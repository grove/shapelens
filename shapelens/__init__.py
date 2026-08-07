"""Deterministic, local SHACL-derived query runtime."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import rdflib
from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.plugins.sparql.parser import parseQuery


__version__ = "0.1.0"
COMPILER_VERSION = "shapelens-0.1"

# Exact RDF-term identity requires preserving source lexical forms.
rdflib.NORMALIZE_LITERALS = False


class ShapeLensError(Exception):
    """Base error for invalid trusted configuration or caller input."""


class CatalogError(ShapeLensError):
    pass


class PlanError(ShapeLensError, ValueError):
    pass


class UnsupportedPlan(PlanError):
    pass


class AuthorizationError(PlanError):
    pass


class PolicyError(PlanError):
    pass


class EvidenceError(ShapeLensError):
    pass


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(domain.encode() + b"\0" + encoded).hexdigest()


def _iri(value: Any) -> str:
    if not isinstance(value, str) or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:.+$", value):
        raise PlanError("absolute IRI required")
    tail = value[value.index(":") + 1 :]
    if any(
        ord(char) <= 0x20
        or 0xD800 <= ord(char) <= 0xDFFF
        or char in '<>"{}|^`\\'
        for char in tail
    ):
        raise PlanError("absolute IRI required")
    return value


def _required_string(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise PlanError(f"non-empty {name} required")
    return value


def _only(raw: Mapping[str, Any], allowed: set[str], label: str) -> None:
    if any(not isinstance(key, str) for key in raw):
        raise PlanError(f"{label} field names must be strings")
    extras = set(raw) - allowed
    if extras:
        raise PlanError(f"unknown {label} fields: {', '.join(sorted(extras))}")


def _items(raw: Mapping[str, Any], name: str, maximum: int) -> list[Mapping[str, Any]]:
    value = raw.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise PlanError(f"{name} must be an array of objects")
    if len(value) > maximum:
        raise PolicyError(f"{name} exceeds policy limit")
    return value


@dataclass(frozen=True)
class Term:
    kind: str
    value: str
    datatype: str | None = None
    language: str | None = None

    @classmethod
    def load(cls, raw: Mapping[str, Any]) -> "Term":
        if not isinstance(raw, Mapping):
            raise PlanError("RDF term must be an object")
        _only(raw, {"kind", "value", "datatype", "language"}, "RDF term")
        kind, value = raw.get("kind"), raw.get("value")
        if kind == "iri":
            if raw.get("datatype") is not None or raw.get("language") is not None:
                raise PlanError("IRI cannot have datatype or language")
            return cls("iri", _iri(value))
        if kind != "literal" or not isinstance(value, str):
            raise PlanError("valid RDF term required")
        datatype, language = raw.get("datatype"), raw.get("language")
        if datatype is not None and language is not None:
            raise PlanError("literal cannot have both datatype and language")
        if datatype is not None:
            datatype = _iri(datatype)
        if language is not None:
            if not isinstance(language, str) or not re.fullmatch(
                r"[A-Za-z]+(?:-[A-Za-z0-9]+)*", language
            ):
                raise PlanError("valid language tag required")
            language = language.lower()
        return cls("literal", value, datatype, language)

    @classmethod
    def from_rdf(cls, value: Any) -> "Term":
        if isinstance(value, URIRef):
            return cls.load({"kind": "iri", "value": str(value)})
        if isinstance(value, Literal):
            return cls.load(
                {
                    "kind": "literal",
                    "value": str(value),
                    "datatype": str(value.datatype) if value.datatype else None,
                    "language": value.language,
                }
            )
        raise PlanError("only IRI and literal result terms are supported")

    def rdf(self) -> URIRef | Literal:
        if self.kind == "iri":
            return URIRef(self.value)
        return Literal(
            self.value,
            datatype=URIRef(self.datatype) if self.datatype else None,
            lang=self.language,
        )

    def sparql(self) -> str:
        if self.kind == "iri":
            return f"<{self.value}>"
        text = (
            self.value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\t", "\\t")
            .replace("\b", "\\b")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\f", "\\f")
        )
        if self.language:
            return f'"{text}"@{self.language}'
        if self.datatype:
            return f'"{text}"^^<{self.datatype}>'
        return f'"{text}"'

    def sort_key(self) -> tuple[str, str, str, str]:
        return self.kind, self.value, self.datatype or "", self.language or ""


@dataclass(frozen=True)
class QualificationRecord:
    shape_term: str
    behavior: str
    value: str
    fixture_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.shape_term, str)
            or not self.shape_term
            or not isinstance(self.value, str)
            or not self.value
            or not isinstance(self.behavior, str)
            or self.behavior not in {"selector", "property", "scalar_projection"}
        ):
            raise CatalogError("unknown qualification behavior")
        if (
            not isinstance(self.fixture_ids, tuple)
            or not self.fixture_ids
            or any(not isinstance(x, str) or not x for x in self.fixture_ids)
            or len(self.fixture_ids) != len(set(self.fixture_ids))
        ):
            raise CatalogError("qualification requires fixture coverage")


@dataclass(frozen=True)
class SemanticQualification:
    owner: str
    fixture_revision: str
    records: tuple[QualificationRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(record, QualificationRecord) for record in self.records
        ):
            raise CatalogError("qualification records must be exact typed records")
        keys = [(x.shape_term, x.behavior, x.value) for x in self.records]
        if (
            not isinstance(self.owner, str)
            or not self.owner
            or not isinstance(self.fixture_revision, str)
            or not self.fixture_revision
            or len(keys) != len(set(keys))
        ):
            raise CatalogError("qualification owner, revision, and unique exact records required")

    def covers(self, shape: str, behavior: str, value: str) -> bool:
        return any(
            record.shape_term == shape
            and record.behavior == behavior
            and record.value == value
            for record in self.records
        )

    @classmethod
    def reviewed_graph(
        cls,
        graph: Graph,
        *,
        owner: str,
        fixture_revision: str,
        fixture_ids: Sequence[str],
    ) -> "SemanticQualification":
        """Create exact records after the caller asserts every supported field was reviewed."""
        fixtures = tuple(fixture_ids)
        records: list[QualificationRecord] = []
        for shape in sorted(set(graph.subjects(RDF.type, SH.NodeShape)), key=str):
            shape_term = str(shape)
            classes = sorted(str(x) for x in graph.objects(shape, SH.targetClass) if isinstance(x, URIRef))
            targets = sorted(str(x) for x in graph.objects(shape, SH.targetNode) if isinstance(x, URIRef))
            if classes or targets:
                records.append(
                    QualificationRecord(
                        shape_term,
                        "selector",
                        _selector_signature(classes, targets),
                        fixtures,
                    )
                )
            for prop_shape in sorted(graph.objects(shape, SH.property), key=str):
                path = _supported_path(graph, prop_shape)
                if path is None:
                    continue
                predicate, inverse = path
                signature = _property_signature(graph, prop_shape, predicate, inverse)
                records.append(QualificationRecord(shape_term, "property", signature, fixtures))
                if graph.value(prop_shape, SH.maxCount) == Literal(1):
                    records.append(
                        QualificationRecord(shape_term, "scalar_projection", signature, fixtures)
                    )
        return cls(owner, fixture_revision, tuple(records))


@dataclass(frozen=True)
class ShapeSource:
    graph: Graph
    source_id: str
    owner: str
    trust: str
    qualification: SemanticQualification
    closure_trust: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.graph, Graph)
            or not isinstance(self.source_id, str)
            or not self.source_id
            or not isinstance(self.owner, str)
            or not self.owner
            or not isinstance(self.qualification, SemanticQualification)
            or not isinstance(self.closure_trust, tuple)
        ):
            raise CatalogError("shape graph, source ID, and owner required")
        if not isinstance(self.trust, str) or self.trust not in {"trusted", "untrusted", "quarantined"} or any(
            not isinstance(value, str) or value not in {"trusted", "untrusted", "quarantined"}
            for value in self.closure_trust
        ):
            raise CatalogError("invalid source trust")

    @property
    def executable_trust(self) -> bool:
        return self.trust == "trusted" and all(x == "trusted" for x in self.closure_trust)


@dataclass(frozen=True)
class ApplicationOverlay:
    overlay_id: str
    kind: str
    owner: str
    trusted: bool = False
    scalar_projections: tuple[tuple[str, str], ...] = ()
    qualification: SemanticQualification | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.overlay_id, str)
            or not self.overlay_id
            or not isinstance(self.owner, str)
            or not self.owner
            or type(self.trusted) is not bool
        ):
            raise CatalogError("overlay ID, owner, and Boolean trust are required")
        if not isinstance(self.kind, str) or self.kind not in {"descriptive", "executable", "policy"}:
            raise CatalogError("overlay must be descriptive, executable, or policy")
        if self.scalar_projections and self.kind != "executable":
            raise CatalogError("only executable overlays may add projection contracts")
        if self.qualification is not None and not isinstance(
            self.qualification, SemanticQualification
        ):
            raise CatalogError("overlay qualification must be typed")
        if not isinstance(self.scalar_projections, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or any(not isinstance(value, str) or not value for value in item)
            for item in self.scalar_projections
        ):
            raise CatalogError("scalar projection references must be shape/predicate pairs")


@dataclass(frozen=True)
class CatalogPolicy:
    max_source_bytes: int = 1_000_000
    max_source_triples: int = 20_000
    max_rdf_list_length: int = 100
    max_recursion_depth: int = 16
    max_path_depth: int = 4
    max_lens_card_bytes: int = 16_000

    def __post_init__(self) -> None:
        values = (
            self.max_source_bytes,
            self.max_source_triples,
            self.max_rdf_list_length,
            self.max_recursion_depth,
            self.max_path_depth,
            self.max_lens_card_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise CatalogError("catalog limits must be finite positive integers")


@dataclass(frozen=True)
class ContractBranch:
    key: str
    portable_key: str | None
    classes: tuple[str, ...] = ()
    datatypes: tuple[str, ...] = ()
    node_kinds: tuple[str, ...] = ()
    allowed_terms: tuple[Term, ...] = ()

    def accepts(self, term: Term) -> bool:
        if self.classes and term.kind != "iri":
            return False
        if self.datatypes:
            effective = term.datatype or (
                str(RDF.langString) if term.language else "http://www.w3.org/2001/XMLSchema#string"
            )
            if term.kind != "literal" or effective not in self.datatypes:
                return False
        if self.node_kinds:
            compatible = {
                str(SH.IRI): term.kind == "iri",
                str(SH.Literal): term.kind == "literal",
                str(SH.BlankNodeOrIRI): term.kind == "iri",
                str(SH.BlankNodeOrLiteral): term.kind == "literal",
                str(SH.IRIOrLiteral): True,
            }
            if not all(compatible.get(kind, False) for kind in self.node_kinds):
                return False
        return not self.allowed_terms or term in self.allowed_terms

    @property
    def accepts_iri(self) -> bool:
        if self.datatypes or str(SH.Literal) in self.node_kinds or str(SH.BlankNodeOrLiteral) in self.node_kinds:
            return False
        return not self.allowed_terms or any(term.kind == "iri" for term in self.allowed_terms)


@dataclass(frozen=True)
class LensDef:
    key: str
    portable_key: str | None
    shape_term: str
    source_id: str
    trusted: bool


@dataclass(frozen=True)
class SelectorDef:
    key: str
    portable_key: str | None
    lens_key: str
    classes: tuple[str, ...]
    target_iris: tuple[str, ...]
    trusted: bool
    qualified: bool

    @property
    def kind(self) -> str:
        if self.classes and self.target_iris:
            return "union"
        return "direct_type" if self.classes else "target_nodes"


@dataclass(frozen=True)
class PropertyDef:
    key: str
    portable_key: str | None
    lens_key: str
    source_term: str
    predicate_iri: str
    inverse: bool
    branches: tuple[ContractBranch, ...]
    scalar: bool
    trusted: bool
    qualified: bool

    @property
    def branch_keys(self) -> tuple[str, ...]:
        return tuple(branch.key for branch in self.branches)


@dataclass(frozen=True)
class Diagnostic:
    source_id: str
    shape_term: str
    code: str
    detail: str


def _catalog_payload(
    schema_version: int,
    build_scope: str,
    lenses: Sequence[LensDef],
    selectors: Sequence[SelectorDef],
    properties: Sequence[PropertyDef],
    diagnostics: Sequence[Diagnostic],
    overlays: Sequence[ApplicationOverlay],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "build_scope": build_scope,
        "lenses": [asdict(item) for item in lenses],
        "selectors": [asdict(item) for item in selectors],
        "properties": [asdict(item) for item in properties],
        "diagnostics": [asdict(item) for item in diagnostics],
        "overlays": [asdict(item) for item in overlays],
    }


def _selector_signature(classes: Sequence[str], targets: Sequence[str]) -> str:
    return json.dumps({"classes": sorted(classes), "targets": sorted(targets)}, separators=(",", ":"))


def _contract_material(
    graph: Graph,
    node: Any,
    maximum: int,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[Term, ...]]:
    raw_classes = tuple(graph.objects(node, SH["class"]))
    raw_datatypes = tuple(graph.objects(node, SH.datatype))
    raw_node_kinds = tuple(graph.objects(node, SH.nodeKind))
    if any(not isinstance(x, URIRef) for x in (*raw_classes, *raw_datatypes, *raw_node_kinds)):
        raise CatalogError("class, datatype, and node-kind constraints must be IRIs")
    supported_node_kinds = {
        SH.IRI,
        SH.Literal,
        SH.BlankNodeOrIRI,
        SH.BlankNodeOrLiteral,
        SH.IRIOrLiteral,
    }
    if any(x not in supported_node_kinds for x in raw_node_kinds):
        raise CatalogError("unsupported node-kind constraint")
    try:
        classes = tuple(sorted(_iri(str(x)) for x in raw_classes))
        datatypes = tuple(sorted(_iri(str(x)) for x in raw_datatypes))
        node_kinds = tuple(sorted(_iri(str(x)) for x in raw_node_kinds))
    except PlanError as exc:
        raise CatalogError("invalid contract IRI") from exc
    in_lists = tuple(graph.objects(node, SH["in"]))
    if len(in_lists) > 1:
        raise CatalogError("multiple sh:in lists are not supported")
    try:
        allowed = tuple(
            Term.from_rdf(term)
            for term in (_read_list(graph, in_lists[0], maximum) if in_lists else ())
        )
    except PlanError as exc:
        raise CatalogError("sh:in contains an unsupported RDF term") from exc
    return classes, datatypes, node_kinds, allowed


def _property_signature(
    graph: Graph,
    prop_shape: Any,
    predicate: str,
    inverse: bool,
    maximum: int = 100,
) -> str:
    branches = []
    for node in _branch_nodes(graph, prop_shape, maximum):
        classes, datatypes, node_kinds, allowed = _contract_material(graph, node, maximum)
        branches.append(
            {
                "classes": classes,
                "datatypes": datatypes,
                "node_kinds": node_kinds,
                "allowed_terms": [asdict(term) for term in allowed],
            }
        )
    return json.dumps(
        {"predicate": predicate, "inverse": inverse, "branches": branches},
        sort_keys=True,
        separators=(",", ":"),
    )


def _supported_path(graph: Graph, prop_shape: Any) -> tuple[str, bool] | None:
    paths = tuple(graph.objects(prop_shape, SH.path))
    if len(paths) != 1:
        return None
    path, inverse = paths[0], False
    if isinstance(path, BNode):
        inverse_paths = tuple(graph.objects(path, SH.inversePath))
        if len(inverse_paths) != 1:
            return None
        path, inverse = inverse_paths[0], True
    return (str(path), inverse) if isinstance(path, URIRef) else None


def _read_list(graph: Graph, head: Any, maximum: int) -> tuple[Any, ...]:
    values: list[Any] = []
    seen: set[Any] = set()
    while head != RDF.nil:
        if head in seen or len(values) >= maximum:
            raise CatalogError("cyclic or oversized RDF list")
        seen.add(head)
        first = tuple(graph.objects(head, RDF.first))
        rest = tuple(graph.objects(head, RDF.rest))
        if len(first) != 1 or len(rest) != 1:
            raise CatalogError("malformed RDF list")
        values.append(first[0])
        head = rest[0]
    return tuple(values)


def _branch_nodes(graph: Graph, prop_shape: Any, maximum: int) -> tuple[Any, ...]:
    alternatives = tuple(graph.objects(prop_shape, SH["or"]))
    if not alternatives:
        return (prop_shape,)
    if len(alternatives) != 1:
        raise CatalogError("property shape has multiple sh:or lists")
    nodes = _read_list(graph, alternatives[0], maximum)
    if not nodes:
        raise CatalogError("empty sh:or is not executable")
    return nodes


def _check_recursion(
    graph: Graph,
    node: Any,
    maximum: int,
    list_maximum: int,
    trail: tuple[Any, ...] = (),
) -> None:
    if node in trail or len(trail) >= maximum:
        raise CatalogError("cyclic or over-depth nested shape contract")
    nested_nodes = list(graph.objects(node, SH.node))
    for prop_shape in graph.objects(node, SH.property):
        nested_nodes.extend(graph.objects(prop_shape, SH.node))
        for head in graph.objects(prop_shape, SH["or"]):
            for branch in _read_list(graph, head, list_maximum):
                nested_nodes.extend(graph.objects(branch, SH.node))
    for nested in nested_nodes:
        _check_recursion(graph, nested, maximum, list_maximum, (*trail, node))


def _contract_branch(
    graph: Graph,
    node: Any,
    *,
    key: str,
    portable_key: str | None,
    maximum: int,
) -> ContractBranch:
    classes, datatypes, node_kinds, allowed = _contract_material(graph, node, maximum)
    return ContractBranch(key, portable_key, classes, datatypes, node_kinds, allowed)


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    revision: str
    build_scope: str
    lenses: tuple[LensDef, ...]
    selectors: tuple[SelectorDef, ...]
    properties: tuple[PropertyDef, ...]
    diagnostics: tuple[Diagnostic, ...]
    overlays: tuple[ApplicationOverlay, ...] = field(repr=False)

    def __post_init__(self) -> None:
        groups = (
            (self.lenses, LensDef),
            (self.selectors, SelectorDef),
            (self.properties, PropertyDef),
            (self.diagnostics, Diagnostic),
            (self.overlays, ApplicationOverlay),
        )
        if (
            self.schema_version != 1
            or not isinstance(self.build_scope, str)
            or not self.build_scope
            or any(
                not isinstance(items, tuple)
                or any(not isinstance(item, expected) for item in items)
                for items, expected in groups
            )
        ):
            raise CatalogError("catalog must be a typed immutable version 1 artifact")
        payload = _catalog_payload(
            self.schema_version,
            self.build_scope,
            self.lenses,
            self.selectors,
            self.properties,
            self.diagnostics,
            self.overlays,
        )
        if self.revision != _digest("catalog", payload):
            raise CatalogError("catalog revision does not match its immutable contents")

    @classmethod
    def build(
        cls,
        sources: Iterable[ShapeSource],
        *,
        overlays: Iterable[ApplicationOverlay] = (),
        build_id: str | None = None,
        policy: CatalogPolicy | None = None,
    ) -> "Catalog":
        policy = policy or CatalogPolicy()
        if not isinstance(policy, CatalogPolicy):
            raise CatalogError("catalog policy must be typed")
        sources, overlays = tuple(sources), tuple(overlays)
        if not sources:
            raise CatalogError("at least one shape source required")
        if any(not isinstance(source, ShapeSource) for source in sources) or any(
            not isinstance(overlay, ApplicationOverlay) for overlay in overlays
        ):
            raise CatalogError("typed shape sources and overlays required")
        if len({source.source_id for source in sources}) != len(sources):
            raise CatalogError("unique shape source IDs required")
        rows: list[tuple[str, str, str, str]] = []
        for source in sources:
            if len(source.graph) > policy.max_source_triples:
                raise CatalogError("shape source exceeds triple limit")
            serialized = source.graph.serialize(format="nt", encoding="utf-8")
            if len(serialized) > policy.max_source_bytes:
                raise CatalogError("shape source exceeds byte limit")
            rows.extend((source.source_id, str(s), str(p), str(o)) for s, p, o in source.graph)
        scope = _digest(
            "catalog-build",
            {
                "build_id": build_id or str(uuid.uuid4()),
                "triples": sorted(rows),
                "sources": [
                    {
                        "source_id": x.source_id,
                        "owner": x.owner,
                        "trust": x.trust,
                        "closure_trust": x.closure_trust,
                        "qualification": asdict(x.qualification),
                    }
                    for x in sources
                ],
                "overlays": [asdict(x) for x in overlays],
                "compiler": COMPILER_VERSION,
            },
        )
        lenses: list[LensDef] = []
        selectors: list[SelectorDef] = []
        properties: list[PropertyDef] = []
        diagnostics: list[Diagnostic] = []
        executable_overlays = tuple(
            overlay
            for overlay in overlays
            if overlay.kind == "executable"
            and overlay.trusted
            and overlay.qualification is not None
        )
        for source in sources:
            if source.trust == "quarantined":
                continue
            graph = source.graph
            for node in sorted(set(graph.subjects(RDF.type, SH.NodeShape)), key=str):
                _check_recursion(
                    graph,
                    node,
                    policy.max_recursion_depth,
                    policy.max_rdf_list_length,
                )
                shape_term = str(node)
                if isinstance(node, URIRef):
                    try:
                        _iri(shape_term)
                    except PlanError as exc:
                        raise CatalogError("invalid node-shape IRI") from exc
                lens_index = len(lenses)
                lens_key = f"{scope}:lens:{lens_index}"
                portable_lens = f"shapelens:lens:{shape_term}" if isinstance(node, URIRef) else None
                lenses.append(
                    LensDef(lens_key, portable_lens, shape_term, source.source_id, source.executable_trust)
                )
                try:
                    classes = tuple(sorted(_iri(str(x)) for x in graph.objects(node, SH.targetClass) if isinstance(x, URIRef)))
                    targets = tuple(sorted(_iri(str(x)) for x in graph.objects(node, SH.targetNode) if isinstance(x, URIRef)))
                except PlanError as exc:
                    raise CatalogError("invalid selector IRI") from exc
                invalid_classes = tuple(x for x in graph.objects(node, SH.targetClass) if not isinstance(x, URIRef))
                invalid_targets = tuple(x for x in graph.objects(node, SH.targetNode) if not isinstance(x, URIRef))
                if invalid_classes:
                    diagnostics.append(Diagnostic(source.source_id, shape_term, "target_class_non_iri", "non-IRI target class is diagnostic-only"))
                if invalid_targets:
                    diagnostics.append(Diagnostic(source.source_id, shape_term, "target_node_non_iri", "non-IRI target is diagnostic-only"))
                if classes or targets:
                    signature = _selector_signature(classes, targets)
                    selector_index = len(selectors)
                    portable = (
                        f"shapelens:selector:{shape_term}:{_digest('selector', signature)}"
                        if isinstance(node, URIRef)
                        else None
                    )
                    selectors.append(
                        SelectorDef(
                            f"{scope}:selector:{selector_index}",
                            portable,
                            lens_key,
                            classes,
                            targets,
                            source.executable_trust,
                            source.qualification.covers(shape_term, "selector", signature),
                        )
                    )
                for prop_shape in sorted(graph.objects(node, SH.property), key=str):
                    path = _supported_path(graph, prop_shape)
                    if path is None:
                        diagnostics.append(Diagnostic(source.source_id, shape_term, "path_unsupported", str(prop_shape)))
                        continue
                    predicate, inverse = path
                    try:
                        _iri(predicate)
                    except PlanError as exc:
                        raise CatalogError("invalid property path IRI") from exc
                    if (2 if inverse else 1) > policy.max_path_depth:
                        diagnostics.append(Diagnostic(source.source_id, shape_term, "path_depth_exceeded", str(prop_shape)))
                        continue
                    prop_index = len(properties)
                    prop_key = f"{scope}:property:{prop_index}"
                    portable_prop = (
                        f"shapelens:property:{shape_term}:{prop_shape}"
                        if isinstance(node, URIRef) and isinstance(prop_shape, URIRef)
                        else None
                    )
                    branches = tuple(
                        _contract_branch(
                            graph,
                            branch_node,
                            key=f"{scope}:branch:{prop_index}:{branch_index}",
                            portable_key=(f"{portable_prop}:branch:{branch_index}" if portable_prop else None),
                            maximum=policy.max_rdf_list_length,
                        )
                        for branch_index, branch_node in enumerate(
                            _branch_nodes(graph, prop_shape, policy.max_rdf_list_length)
                        )
                    )
                    signature = _property_signature(
                        graph,
                        prop_shape,
                        predicate,
                        inverse,
                        policy.max_rdf_list_length,
                    )
                    qualified = source.qualification.covers(shape_term, "property", signature)
                    scalar_contract = graph.value(prop_shape, SH.maxCount) == Literal(1)
                    scalar_qualified = source.qualification.covers(
                        shape_term, "scalar_projection", signature
                    )
                    overlay_scalar = any(
                        (shape_term, predicate) in overlay.scalar_projections
                        and overlay.qualification.covers(
                            shape_term, "scalar_projection", signature
                        )
                        for overlay in executable_overlays
                    )
                    properties.append(
                        PropertyDef(
                            prop_key,
                            portable_prop,
                            lens_key,
                            str(prop_shape),
                            predicate,
                            inverse,
                            branches,
                            qualified and (scalar_contract and scalar_qualified or overlay_scalar),
                            source.executable_trust,
                            qualified,
                        )
                    )
        for lens in lenses:
            material = {
                "lens": asdict(lens),
                "selectors": [asdict(x) for x in selectors if x.lens_key == lens.key],
                "properties": [asdict(x) for x in properties if x.lens_key == lens.key],
            }
            if len(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()) > policy.max_lens_card_bytes:
                raise CatalogError("lens material exceeds byte limit")
        payload = _catalog_payload(1, scope, lenses, selectors, properties, diagnostics, overlays)
        revision = _digest("catalog", payload)
        return cls(1, revision, scope, tuple(lenses), tuple(selectors), tuple(properties), tuple(diagnostics), overlays)

    def dump(self) -> dict[str, Any]:
        payload = _catalog_payload(
            self.schema_version,
            self.build_scope,
            self.lenses,
            self.selectors,
            self.properties,
            self.diagnostics,
            self.overlays,
        )
        return {**payload, "revision": self.revision}

    @classmethod
    def reload(cls, raw: Mapping[str, Any]) -> "Catalog":
        if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
            raise CatalogError("unsupported catalog schema")
        try:
            build_scope = raw["build_scope"]
            lenses = tuple(LensDef(**item) for item in raw["lenses"])
            selectors = tuple(
                SelectorDef(**{**item, "classes": tuple(item["classes"]), "target_iris": tuple(item["target_iris"])})
                for item in raw["selectors"]
            )
            properties = tuple(
                PropertyDef(
                    **{
                        **item,
                        "branches": tuple(
                            ContractBranch(
                                **{
                                    **branch,
                                    "classes": tuple(branch["classes"]),
                                    "datatypes": tuple(branch["datatypes"]),
                                    "node_kinds": tuple(branch["node_kinds"]),
                                    "allowed_terms": tuple(Term(**term) for term in branch["allowed_terms"]),
                                }
                            )
                            for branch in item["branches"]
                        ),
                    }
                )
                for item in raw["properties"]
            )
            diagnostics = tuple(Diagnostic(**item) for item in raw["diagnostics"])
            overlays = tuple(
                ApplicationOverlay(
                    **{
                        **item,
                        "scalar_projections": tuple(tuple(x) for x in item["scalar_projections"]),
                        "qualification": (
                            SemanticQualification(
                                owner=item["qualification"]["owner"],
                                fixture_revision=item["qualification"]["fixture_revision"],
                                records=tuple(QualificationRecord(**{**record, "fixture_ids": tuple(record["fixture_ids"])}) for record in item["qualification"]["records"]),
                            )
                            if item.get("qualification")
                            else None
                        ),
                    }
                )
                for item in raw["overlays"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogError("invalid catalog artifact") from exc
        payload = _catalog_payload(
            1,
            build_scope,
            lenses,
            selectors,
            properties,
            diagnostics,
            overlays,
        )
        revision = _digest("catalog", payload)
        if raw.get("revision") != revision:
            raise CatalogError("catalog artifact integrity failure")
        return cls(1, revision, build_scope, lenses, selectors, properties, diagnostics, overlays)

@dataclass(frozen=True)
class Entity:
    id: str
    bound: Term | None


@dataclass(frozen=True)
class SelectorUse:
    id: str
    entity: str
    key: str


@dataclass(frozen=True)
class LensUse:
    id: str
    entity: str
    key: str


@dataclass(frozen=True)
class Edge:
    id: str
    source_lens: str
    property_key: str
    branch_key: str
    target_entity: str


@dataclass(frozen=True)
class Eq:
    id: str
    lens: str
    property_key: str
    branch_key: str
    value: Term


@dataclass(frozen=True)
class Exists:
    id: str
    lens: str
    property_key: str


@dataclass(frozen=True)
class NodeProjection:
    id: str
    entity: str


@dataclass(frozen=True)
class FieldProjection:
    id: str
    lens: str
    property_key: str
    branch_key: str
    required: bool


@dataclass(frozen=True)
class Plan:
    kind: str
    catalog_revision: str
    entities: tuple[Entity, ...]
    selectors: tuple[SelectorUse, ...]
    lenses: tuple[LensUse, ...]
    edges: tuple[Edge, ...]
    filters: tuple[Eq | Exists, ...]
    projections: tuple[NodeProjection | FieldProjection, ...]


@dataclass(frozen=True)
class QueryPolicy:
    revision: str = "shapelens:policy:safe-local-0.1"
    max_entities: int = 16
    max_selectors: int = 16
    max_lenses: int = 32
    max_edges: int = 32
    max_filters: int = 32
    max_projections: int = 32
    max_ast_nodes: int = 128
    max_result_rows: int = 1_000
    max_result_bytes: int = 2_000_000
    deadline_seconds: float = 10.0
    max_retries: int = 0
    max_auxiliary_queries: int = 1
    max_structural_expansion_depth: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.max_entities,
            self.max_selectors,
            self.max_lenses,
            self.max_edges,
            self.max_filters,
            self.max_projections,
            self.max_ast_nodes,
            self.max_result_rows,
            self.max_result_bytes,
        )
        if (
            not isinstance(self.revision, str)
            or not self.revision
            or any(type(value) is not int or value <= 0 for value in counts)
            or type(self.deadline_seconds) not in {int, float}
            or not math.isfinite(self.deadline_seconds)
            or self.deadline_seconds <= 0
            or type(self.max_retries) is not int
            or self.max_retries != 0
            or type(self.max_auxiliary_queries) is not int
            or self.max_auxiliary_queries < 0
            or type(self.max_structural_expansion_depth) is not int
            or self.max_structural_expansion_depth != 0
        ):
            raise PolicyError("finite positive local policy limits required; retries are disabled")


@dataclass(frozen=True)
class AuthorizationScope:
    scope_id: str
    allowed_lenses: frozenset[str] | None = None
    allowed_selectors: frozenset[str] | None = None
    allowed_properties: frozenset[str] | None = None
    allowed_graphs: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope_id, str) or not self.scope_id:
            raise PolicyError("authorization scope ID required")
        for values in (
            self.allowed_lenses,
            self.allowed_selectors,
            self.allowed_properties,
            self.allowed_graphs,
        ):
            if values is not None and (
                not isinstance(values, frozenset)
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise PolicyError("authorization allowlists must be frozensets of non-empty strings")
        if self.allowed_graphs is not None:
            for graph in self.allowed_graphs:
                _iri(graph)

    @property
    def digest(self) -> str:
        return _digest(
            "authorization",
            {
                "scope_id": self.scope_id,
                "allowed_lenses": sorted(self.allowed_lenses) if self.allowed_lenses is not None else None,
                "allowed_selectors": sorted(self.allowed_selectors) if self.allowed_selectors is not None else None,
                "allowed_properties": sorted(self.allowed_properties) if self.allowed_properties is not None else None,
                "allowed_graphs": sorted(self.allowed_graphs) if self.allowed_graphs is not None else None,
            },
        )

    @classmethod
    def allow_all(cls, scope_id: str = "local-all") -> "AuthorizationScope":
        return cls(scope_id)


@dataclass(frozen=True)
class DatasetScope:
    dataset_id: str
    graph_iris: tuple[str, ...] = ()
    default_graph_mode: str = "store_default"
    entailment_regime: str = "none"
    dataset_revision: str | None = None
    consistency: str = "single_query"

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id:
            raise PolicyError("dataset scope ID required")
        if not isinstance(self.graph_iris, tuple) or any(
            not isinstance(graph, str) for graph in self.graph_iris
        ):
            raise PolicyError("named graph scope must be a tuple")
        object.__setattr__(self, "graph_iris", tuple(sorted(set(self.graph_iris))))
        if not isinstance(self.default_graph_mode, str) or self.default_graph_mode not in {"store_default", "explicit_default", "union"}:
            raise PolicyError("invalid default graph mode")
        if not isinstance(self.entailment_regime, str) or self.entailment_regime not in {"none", "simple", "rdfs"}:
            raise PolicyError("unsupported entailment regime")
        if not isinstance(self.consistency, str) or self.consistency not in {"snapshot", "single_query", "best_effort"}:
            raise PolicyError("invalid consistency")
        for graph in self.graph_iris:
            _iri(graph)

    @property
    def digest(self) -> str:
        return _digest("dataset-scope", asdict(self))


def _unique(items: Iterable[Any], label: str) -> None:
    values = [x.id for x in items]
    if any(not isinstance(x, str) or not x for x in values) or len(values) != len(set(values)):
        raise PlanError(f"unique {label} IDs required")


def _validate_policy_size(plan: Plan, policy: QueryPolicy) -> None:
    limits = (
        (len(plan.entities), policy.max_entities, "entities"),
        (len(plan.selectors), policy.max_selectors, "selectors"),
        (len(plan.lenses), policy.max_lenses, "lenses"),
        (len(plan.edges), policy.max_edges, "edges"),
        (len(plan.filters), policy.max_filters, "filters"),
        (len(plan.projections), policy.max_projections, "projections"),
    )
    for actual, maximum, label in limits:
        if actual > maximum:
            raise PolicyError(f"{label} exceeds policy limit")


def normalize_plan(raw: Mapping[str, Any], catalog: Catalog, policy: QueryPolicy) -> Plan:
    if not isinstance(raw, Mapping):
        raise PlanError("plan must be an object")
    _only(
        raw,
        {"kind", "catalog_revision", "entities", "selectors", "lenses", "edges", "filters", "projections"},
        "plan",
    )
    kind = raw.get("kind")
    if kind == "boolean":
        kind = "ask"
    if not isinstance(kind, str) or kind not in {"select", "ask"}:
        raise UnsupportedPlan("only select and ask plans are supported")
    if raw.get("catalog_revision") != catalog.revision:
        raise PlanError("catalog revision mismatch")
    try:
        entity_items = _items(raw, "entities", policy.max_entities)
        for item in entity_items:
            _only(item, {"id", "binding"}, "entity")
        entities = tuple(
            Entity(
                _required_string(x, "id"),
                Term.load(x["binding"]) if x.get("binding") is not None else None,
            )
            for x in entity_items
        )
        selector_items = _items(raw, "selectors", policy.max_selectors)
        for item in selector_items:
            _only(item, {"id", "entity", "key"}, "selector")
        selectors = tuple(
            SelectorUse(_required_string(x, "id"), _required_string(x, "entity"), _required_string(x, "key"))
            for x in selector_items
        )
        lens_items = _items(raw, "lenses", policy.max_lenses)
        for item in lens_items:
            _only(item, {"id", "entity", "key"}, "lens")
        lenses = tuple(
            LensUse(_required_string(x, "id"), _required_string(x, "entity"), _required_string(x, "key"))
            for x in lens_items
        )
        edge_items = _items(raw, "edges", policy.max_edges)
        for item in edge_items:
            _only(item, {"id", "source_lens", "property_key", "branch_key", "target_entity"}, "edge")
        edges = tuple(
            Edge(
                _required_string(x, "id"),
                _required_string(x, "source_lens"),
                _required_string(x, "property_key"),
                _required_string(x, "branch_key"),
                _required_string(x, "target_entity"),
            )
            for x in edge_items
        )
        filters: list[Eq | Exists] = []
        for x in _items(raw, "filters", policy.max_filters):
            if x.get("kind") == "eq":
                _only(x, {"id", "kind", "lens", "property_key", "branch_key", "value"}, "equality filter")
                filters.append(
                    Eq(
                        _required_string(x, "id"),
                        _required_string(x, "lens"),
                        _required_string(x, "property_key"),
                        _required_string(x, "branch_key"),
                        Term.load(x["value"]),
                    )
                )
            elif x.get("kind") == "exists":
                _only(x, {"id", "kind", "lens", "property_key"}, "existence filter")
                filters.append(
                    Exists(
                        _required_string(x, "id"),
                        _required_string(x, "lens"),
                        _required_string(x, "property_key"),
                    )
                )
            else:
                raise UnsupportedPlan("unsupported filter")
        projections: list[NodeProjection | FieldProjection] = []
        for x in _items(raw, "projections", policy.max_projections):
            if x.get("kind") == "node":
                _only(x, {"id", "kind", "entity"}, "node projection")
                projections.append(NodeProjection(_required_string(x, "id"), _required_string(x, "entity")))
            elif x.get("kind") == "field":
                _only(x, {"id", "kind", "lens", "property_key", "branch_key", "required"}, "field projection")
                if type(x.get("required")) is not bool:
                    raise PlanError("field projection requires an explicit Boolean")
                projections.append(
                    FieldProjection(
                        _required_string(x, "id"),
                        _required_string(x, "lens"),
                        _required_string(x, "property_key"),
                        _required_string(x, "branch_key"),
                        x["required"],
                    )
                )
            else:
                raise UnsupportedPlan("unsupported projection")
    except KeyError as exc:
        raise PlanError(f"missing plan field: {exc.args[0]}") from exc
    if any(entity.bound and entity.bound.kind != "iri" for entity in entities):
        raise PlanError("entity binding must be IRI")
    plan = Plan(kind, catalog.revision, entities, selectors, lenses, edges, tuple(filters), tuple(projections))
    _validate_plan(plan, catalog, policy)
    return _canonical_plan(plan)


def _validate_plan(plan: Plan, catalog: Catalog, policy: QueryPolicy | None = None) -> None:
    if not isinstance(plan, Plan) or not isinstance(plan.kind, str) or plan.kind not in {"select", "ask"}:
        raise UnsupportedPlan("only select and ask plans are supported")
    if plan.catalog_revision != catalog.revision:
        raise PlanError("catalog revision mismatch")
    groups = (
        (plan.entities, Entity),
        (plan.selectors, SelectorUse),
        (plan.lenses, LensUse),
        (plan.edges, Edge),
        (plan.filters, (Eq, Exists)),
        (plan.projections, (NodeProjection, FieldProjection)),
    )
    if any(not isinstance(group, tuple) or any(not isinstance(item, expected) for item in group) for group, expected in groups):
        raise PlanError("plan contains invalid typed items")
    references = [value for item in (*plan.selectors, *plan.lenses) for value in (item.entity, item.key)]
    references.extend(
        value
        for item in plan.edges
        for value in (item.source_lens, item.property_key, item.branch_key, item.target_entity)
    )
    for item in plan.filters:
        references.extend((item.lens, item.property_key))
        if isinstance(item, Eq):
            references.append(item.branch_key)
    for item in plan.projections:
        if isinstance(item, NodeProjection):
            references.append(item.entity)
        else:
            references.extend((item.lens, item.property_key, item.branch_key))
    if any(not isinstance(value, str) or not value for value in references) or any(
        isinstance(item, FieldProjection) and type(item.required) is not bool
        for item in plan.projections
    ):
        raise PlanError("plan references and projection flags must have valid types")
    for entity in plan.entities:
        if entity.bound is not None:
            if not isinstance(entity.bound, Term) or Term.load(asdict(entity.bound)).kind != "iri":
                raise PlanError("entity binding must be IRI")
    for expression in plan.filters:
        if isinstance(expression, Eq):
            if not isinstance(expression.value, Term):
                raise PlanError("equality value must be an RDF term")
            Term.load(asdict(expression.value))
    if policy:
        _validate_policy_size(plan, policy)
    _unique(plan.entities, "entity")
    _unique(plan.selectors, "selector")
    _unique(plan.lenses, "lens")
    _unique(plan.edges, "edge")
    _unique(plan.filters, "filter")
    _unique(plan.projections, "projection")
    if not plan.entities:
        raise PlanError("at least one entity required")
    if (plan.kind == "select" and not plan.projections) or (plan.kind == "ask" and plan.projections):
        raise PlanError("select needs projections; ask has none")
    entities = {x.id: x for x in plan.entities}
    lenses = {x.id: x for x in plan.lenses}
    lens_defs = {x.key: x for x in catalog.lenses}
    selectors = {x.key: x for x in catalog.selectors}
    properties = {x.key: x for x in catalog.properties}
    if len({(x.entity, x.key) for x in plan.lenses}) != len(plan.lenses):
        raise PlanError("duplicate entity/lens use")
    for use in plan.lenses:
        definition = lens_defs.get(use.key)
        if use.entity not in entities or definition is None or not definition.trusted:
            raise PlanError("unknown or untrusted lens use")
    selected: set[str] = set()
    for use in plan.selectors:
        definition = selectors.get(use.key)
        lens = lens_defs.get(definition.lens_key) if definition else None
        if (
            use.entity not in entities
            or definition is None
            or lens is None
            or not definition.trusted
            or not definition.qualified
            or not lens.trusted
        ):
            raise PlanError("unknown, untrusted, or unqualified selector use")
        if use.entity in selected:
            raise UnsupportedPlan("at most one selector use per entity is supported")
        selected.add(use.entity)
    used_lenses: set[str] = set()
    incoming: set[str] = set()
    adjacency = {entity.id: set() for entity in plan.entities}

    def checked(lens_id: str, property_key: str, branch_key: str | None = None) -> tuple[PropertyDef, ContractBranch | None]:
        prop = properties.get(property_key)
        use = lenses.get(lens_id)
        if (
            use is None
            or prop is None
            or prop.lens_key != use.key
            or not prop.trusted
            or not prop.qualified
        ):
            raise PlanError("unknown, untrusted, or unqualified property")
        branch = next((x for x in prop.branches if x.key == branch_key), None) if branch_key else None
        if branch_key and branch is None:
            raise PlanError("unknown contract branch")
        used_lenses.add(lens_id)
        return prop, branch

    for edge in plan.edges:
        _, branch = checked(edge.source_lens, edge.property_key, edge.branch_key)
        if edge.target_entity not in entities:
            raise PlanError("unknown edge target")
        if branch is None or not branch.accepts_iri:
            raise PlanError("edge target is incompatible with contract branch")
        if entities[edge.target_entity].bound and not branch.accepts(entities[edge.target_entity].bound):
            raise PlanError("bound edge target is incompatible with contract branch")
        incoming.add(edge.target_entity)
        source = lenses[edge.source_lens].entity
        adjacency[source].add(edge.target_entity)
        adjacency[edge.target_entity].add(source)
    for expression in plan.filters:
        _, branch = checked(expression.lens, expression.property_key, getattr(expression, "branch_key", None))
        if isinstance(expression, Eq) and branch is None:
            raise PlanError("equality filter requires a contract branch")
        if isinstance(expression, Eq) and branch and not branch.accepts(expression.value):
            raise PlanError("equality term is incompatible with its contract branch")
    for projection in plan.projections:
        if isinstance(projection, NodeProjection):
            if projection.entity not in entities:
                raise PlanError("unknown projection entity")
        else:
            prop, branch = checked(projection.lens, projection.property_key, projection.branch_key)
            if branch is None or not prop.scalar:
                raise UnsupportedPlan("field projection requires a qualified scalar contract")
    semantic_groups = (
        [(x.entity, x.key) for x in plan.selectors],
        [(x.source_lens, x.property_key, x.branch_key, x.target_entity) for x in plan.edges],
        [
            (
                type(x).__name__,
                x.lens,
                x.property_key,
                getattr(x, "branch_key", None),
                json.dumps(asdict(x.value), sort_keys=True) if isinstance(x, Eq) else None,
            )
            for x in plan.filters
        ],
        [
            (type(x).__name__, x.entity)
            if isinstance(x, NodeProjection)
            else (type(x).__name__, x.lens, x.property_key, x.branch_key, x.required)
            for x in plan.projections
        ],
    )
    if any(len(items) != len(set(items)) for items in semantic_groups):
        raise PlanError("duplicate semantic atom")
    if used_lenses != set(lenses):
        raise PlanError("unused lens use")
    for entity in plan.entities:
        if entity.bound is None and entity.id not in incoming and entity.id not in selected:
            raise PlanError("unbound root requires selector")
    seen, todo = set(), [plan.entities[0].id]
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo.extend(adjacency[current] - seen)
    if len(plan.entities) > 1 and seen != set(entities):
        raise PlanError("required edges must connect entities")


def _canonical_plan(plan: Plan) -> Plan:
    lens_by_id = {x.id: x for x in plan.lenses}

    def signature(entity: Entity) -> str:
        return json.dumps(
            {
                "bound": asdict(entity.bound) if entity.bound else None,
                "selectors": sorted(x.key for x in plan.selectors if x.entity == entity.id),
                "lenses": sorted(x.key for x in plan.lenses if x.entity == entity.id),
                "outgoing": sorted(
                    (x.property_key, x.branch_key)
                    for x in plan.edges
                    if lens_by_id[x.source_lens].entity == entity.id
                ),
                "incoming": sorted(
                    (x.property_key, x.branch_key) for x in plan.edges if x.target_entity == entity.id
                ),
                "node_projection": any(
                    isinstance(x, NodeProjection) and x.entity == entity.id for x in plan.projections
                ),
            },
            sort_keys=True,
        )

    entities = sorted(plan.entities, key=signature)
    entity_ids = {x.id: f"e{i}" for i, x in enumerate(entities)}
    lenses = sorted(plan.lenses, key=lambda x: (entity_ids[x.entity], x.key))
    lens_ids = {x.id: f"l{i}" for i, x in enumerate(lenses)}
    selectors = sorted(plan.selectors, key=lambda x: (entity_ids[x.entity], x.key))
    edges = sorted(
        plan.edges,
        key=lambda x: (lens_ids[x.source_lens], x.property_key, x.branch_key, entity_ids[x.target_entity]),
    )
    filters = sorted(
        plan.filters,
        key=lambda x: (
            type(x).__name__,
            lens_ids[x.lens],
            x.property_key,
            getattr(x, "branch_key", ""),
            json.dumps(asdict(x.value), sort_keys=True) if isinstance(x, Eq) else "",
        ),
    )
    projections = sorted(
        plan.projections,
        key=lambda x: (
            type(x).__name__,
            entity_ids[x.entity] if isinstance(x, NodeProjection) else lens_ids[x.lens],
            "" if isinstance(x, NodeProjection) else x.property_key,
            "" if isinstance(x, NodeProjection) else x.branch_key,
        ),
    )
    return Plan(
        plan.kind,
        plan.catalog_revision,
        tuple(Entity(entity_ids[x.id], x.bound) for x in entities),
        tuple(SelectorUse(f"s{i}", entity_ids[x.entity], x.key) for i, x in enumerate(selectors)),
        tuple(LensUse(lens_ids[x.id], entity_ids[x.entity], x.key) for x in lenses),
        tuple(
            Edge(f"a{i}", lens_ids[x.source_lens], x.property_key, x.branch_key, entity_ids[x.target_entity])
            for i, x in enumerate(edges)
        ),
        tuple(
            Eq(f"f{i}", lens_ids[x.lens], x.property_key, x.branch_key, x.value)
            if isinstance(x, Eq)
            else Exists(f"f{i}", lens_ids[x.lens], x.property_key)
            for i, x in enumerate(filters)
        ),
        tuple(
            NodeProjection(f"p{i}", entity_ids[x.entity])
            if isinstance(x, NodeProjection)
            else FieldProjection(f"p{i}", lens_ids[x.lens], x.property_key, x.branch_key, x.required)
            for i, x in enumerate(projections)
        ),
    )


def plan_digest(plan: Plan) -> str:
    return _digest("plan", asdict(plan))


@dataclass(frozen=True)
class TriplePattern:
    subject: str
    predicate: str
    object: str


@dataclass(frozen=True)
class ValuesPattern:
    variable: str
    terms: tuple[Term, ...]


@dataclass(frozen=True)
class SameTermFilter:
    variable: str
    value: Term


@dataclass(frozen=True)
class OptionalPattern:
    patterns: tuple[Any, ...]


@dataclass(frozen=True)
class UnionPattern:
    branches: tuple[tuple[Any, ...], ...]


Pattern = TriplePattern | ValuesPattern | SameTermFilter | OptionalPattern | UnionPattern


@dataclass(frozen=True)
class QueryAST:
    kind: str
    projections: tuple[str, ...]
    patterns: tuple[Pattern, ...]
    limit: int | None = None
    dataset_graphs: tuple[str, ...] = ()


def _render_pattern(pattern: Pattern, indent: str = "  ") -> str:
    if isinstance(pattern, TriplePattern):
        return f"{indent}{pattern.subject} <{pattern.predicate}> {pattern.object} ."
    if isinstance(pattern, ValuesPattern):
        return f"{indent}VALUES {pattern.variable} {{ {' '.join(x.sparql() for x in pattern.terms)} }}"
    if isinstance(pattern, SameTermFilter):
        return f"{indent}FILTER(sameTerm({pattern.variable}, {pattern.value.sparql()}))"
    if isinstance(pattern, OptionalPattern):
        inner = "\n".join(_render_pattern(x, indent + "  ") for x in pattern.patterns)
        return f"{indent}OPTIONAL {{\n{inner}\n{indent}}}"
    branches = []
    for branch in pattern.branches:
        inner = "\n".join(_render_pattern(x, indent + "  ") for x in branch)
        branches.append(f"{indent}{{\n{inner}\n{indent}}}")
    return f"\n{indent}UNION\n".join(branches)


def render_ast(ast: QueryAST) -> str:
    body = "\n".join(_render_pattern(pattern) for pattern in ast.patterns)
    dataset = "".join(f" FROM <{graph}>" for graph in ast.dataset_graphs)
    if ast.kind == "ask":
        query = f"ASK{dataset} WHERE {{\n{body}\n}}"
    else:
        query = f"SELECT DISTINCT {' '.join(ast.projections)}{dataset} WHERE {{\n{body}\n}}"
    if ast.limit is not None:
        query += f"\nLIMIT {ast.limit}"
    parseQuery(query)
    return query


@dataclass(frozen=True)
class CompiledQuery:
    ast: QueryAST
    text: str
    digest: str
    plan_digest: str
    atom_ids: tuple[str, ...]
    public_variables: tuple[str, ...]
    entity_variables: tuple[tuple[str, str], ...]


def _property_pattern(source: str, prop: PropertyDef, target: str) -> TriplePattern:
    return TriplePattern(target, prop.predicate_iri, source) if prop.inverse else TriplePattern(source, prop.predicate_iri, target)


def compile_plan(
    plan: Plan,
    catalog: Catalog,
    *,
    limit: int | None = None,
    policy: QueryPolicy | None = None,
    graph_iris: tuple[str, ...] = (),
) -> CompiledQuery:
    policy = policy or QueryPolicy()
    if not isinstance(policy, QueryPolicy):
        raise PolicyError("query policy must be typed")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise PolicyError("query limit must be a positive integer")
    if not isinstance(graph_iris, tuple):
        raise PolicyError("named graph scope must be a tuple")
    graph_iris = tuple(sorted({_iri(graph) for graph in graph_iris}))
    _validate_plan(plan, catalog, policy)
    plan = _canonical_plan(plan)
    properties = {x.key: x for x in catalog.properties}
    selectors = {x.key: x for x in catalog.selectors}
    lenses = {x.id: x for x in plan.lenses}
    patterns: list[Pattern] = []
    for entity in plan.entities:
        if entity.bound:
            patterns.append(ValuesPattern(f"?{entity.id}", (entity.bound,)))
    for index, use in enumerate(plan.selectors):
        selector, variable = selectors[use.key], f"?{use.entity}"
        class_pattern: tuple[Pattern, ...] = ()
        if selector.classes:
            type_variable = f"?selector_type_{index}"
            class_pattern = (
                ValuesPattern(type_variable, tuple(Term("iri", x) for x in selector.classes)),
                TriplePattern(variable, str(RDF.type), type_variable),
            )
        target_pattern: tuple[Pattern, ...] = ()
        if selector.target_iris:
            target_pattern = (ValuesPattern(variable, tuple(Term("iri", x) for x in selector.target_iris)),)
        if class_pattern and target_pattern:
            patterns.append(UnionPattern((class_pattern, target_pattern)))
        elif class_pattern:
            patterns.extend(class_pattern)
        else:
            patterns.append(target_pattern[0])
    for edge in plan.edges:
        prop = properties[edge.property_key]
        source, target = f"?{lenses[edge.source_lens].entity}", f"?{edge.target_entity}"
        patterns.append(_property_pattern(source, prop, target))
        branch = next(x for x in prop.branches if x.key == edge.branch_key)
        for class_iri in branch.classes:
            patterns.append(TriplePattern(target, str(RDF.type), f"<{class_iri}>"))
        if branch.allowed_terms:
            patterns.append(ValuesPattern(target, branch.allowed_terms))
    for index, expression in enumerate(plan.filters):
        prop = properties[expression.property_key]
        source, value = f"?{lenses[expression.lens].entity}", f"?filter_value_{index}"
        patterns.append(_property_pattern(source, prop, value))
        if isinstance(expression, Eq):
            patterns.append(SameTermFilter(value, expression.value))
            branch = next(x for x in prop.branches if x.key == expression.branch_key)
            for class_iri in branch.classes:
                patterns.append(TriplePattern(value, str(RDF.type), f"<{class_iri}>"))
    public: list[str] = []
    for index, projection in enumerate(plan.projections):
        if isinstance(projection, NodeProjection):
            public.append(f"?{projection.entity}")
        else:
            variable = f"?projection_{index}"
            prop = properties[projection.property_key]
            triple = _property_pattern(f"?{lenses[projection.lens].entity}", prop, variable)
            branch = next(x for x in prop.branches if x.key == projection.branch_key)
            field_patterns: list[Pattern] = [triple]
            field_patterns.extend(
                TriplePattern(variable, str(RDF.type), f"<{class_iri}>")
                for class_iri in branch.classes
            )
            if branch.allowed_terms:
                field_patterns.append(ValuesPattern(variable, branch.allowed_terms))
            if projection.required:
                patterns.extend(field_patterns)
            else:
                patterns.append(OptionalPattern(tuple(field_patterns)))
            public.append(variable)
    entity_variables = tuple((entity.id, f"?{entity.id}") for entity in plan.entities)
    projections = tuple(dict.fromkeys([*public, *(variable for _, variable in entity_variables)]))
    ast = QueryAST(
        plan.kind,
        projections if plan.kind == "select" else (),
        tuple(patterns),
        limit,
        tuple(sorted(graph_iris)),
    )
    def ast_size(pattern: Pattern) -> int:
        if isinstance(pattern, OptionalPattern):
            return 1 + sum(ast_size(item) for item in pattern.patterns)
        if isinstance(pattern, UnionPattern):
            return 1 + sum(ast_size(item) for branch in pattern.branches for item in branch)
        return 1

    nodes = sum(ast_size(pattern) for pattern in patterns)
    if nodes > policy.max_ast_nodes:
        raise PolicyError("compiled query exceeds AST limit")
    text = render_ast(ast)
    return CompiledQuery(
        ast,
        text,
        _digest("query", text),
        plan_digest(plan),
        tuple(x.id for x in plan.selectors + plan.edges + plan.filters + plan.projections),
        tuple(public),
        entity_variables,
    )


@dataclass(frozen=True)
class ExecutionRequest:
    extent: str
    count: int | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        if type(self.cancelled) is not bool:
            raise PolicyError("cancelled must be Boolean")
        if self.extent == "complete" and self.count is None:
            return
        if self.extent == "examples" and type(self.count) is int and self.count > 0:
            return
        raise PolicyError("execution request must be complete or a positive example count")

    @classmethod
    def complete(cls) -> "ExecutionRequest":
        return cls("complete")

    @classmethod
    def examples(cls, count: int) -> "ExecutionRequest":
        if type(count) is not int or count <= 0:
            raise PolicyError("example count must be a positive integer")
        return cls("examples", count)

    @property
    def digest(self) -> str:
        return _digest("execution-request", asdict(self))


@dataclass(frozen=True)
class QueryResultEvidence:
    id: str
    execution_id: str
    plan_digest: str
    query_digest: str
    dataset_scope_digest: str
    authorization_scope_digest: str
    completed: bool
    result_kind: str
    row_count: int
    boolean_value: bool | None
    more_results: bool


@dataclass(frozen=True)
class TriplePatternMatchEvidence:
    id: str
    execution_id: str
    atom_id: str
    subject: Term
    predicate: str
    object: Term
    assertion_status: str = "unknown"


@dataclass(frozen=True)
class RowEvidence:
    id: str
    execution_id: str
    row_key: str
    certificate_id: str


EvidenceItem = QueryResultEvidence | TriplePatternMatchEvidence | RowEvidence


@dataclass(frozen=True)
class EntityBindingEvidence:
    entity_id: str
    term: Term


@dataclass(frozen=True)
class PlanAtomSupport:
    atom_kind: str
    atom_id: str
    status: str
    evidence_ids: tuple[str, ...] = ()
    derived_from_entity_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RowSupportCertificate:
    id: str
    execution_id: str
    plan_digest: str
    query_digest: str
    row_key: str
    entity_bindings: tuple[EntityBindingEvidence, ...]
    plan_atom_support: tuple[PlanAtomSupport, ...]


@dataclass(frozen=True)
class ResultRow:
    key: str
    values: tuple[Term | None, ...]
    entity_bindings: tuple[EntityBindingEvidence, ...]


@dataclass(frozen=True)
class EvidencePacket:
    execution_id: str
    catalog_revision: str
    policy_revision: str
    authorization_scope_digest: str
    dataset_scope: DatasetScope
    plan_digest: str
    request_digest: str
    query_digest: str
    evidence: tuple[EvidenceItem, ...]
    certificates: tuple[RowSupportCertificate, ...]
    execution_complete: bool
    result_extent_satisfied: bool
    result_set_completeness: str


@dataclass(frozen=True)
class Selected:
    kind: str
    rows: tuple[ResultRow, ...]
    packet: EvidencePacket
    degraded: bool = False


@dataclass(frozen=True)
class BooleanResult:
    kind: str
    value: bool
    packet: EvidencePacket


@dataclass(frozen=True)
class NoMatch:
    kind: str
    message: str
    packet: EvidencePacket


@dataclass(frozen=True)
class PolicyLimited:
    kind: str
    reason: str


@dataclass(frozen=True)
class Unsupported:
    kind: str
    reason: str


@dataclass(frozen=True)
class Failed:
    kind: str
    reason: str
    packet: EvidencePacket | None = None


QueryOutcome = Selected | BooleanResult | NoMatch | PolicyLimited | Unsupported | Failed


@dataclass(frozen=True)
class PlanExplanation:
    catalog_revision: str
    plan_digest: str
    authorization_scope_digest: str
    policy_revision: str
    entities: tuple[str, ...]
    selector_uses: tuple[str, ...]
    lens_uses: tuple[str, ...]
    atom_ids: tuple[str, ...]
    query: str
    diagnostics: tuple[Diagnostic, ...]


def _allowed(values: frozenset[str] | None, value: str) -> bool:
    return values is None or value in values


def _authorize(plan: Plan, catalog: Catalog, scope: AuthorizationScope, dataset: DatasetScope) -> None:
    for lens in plan.lenses:
        if not _allowed(scope.allowed_lenses, lens.key):
            raise AuthorizationError("lens use is outside authorization scope")
    for selector in plan.selectors:
        if not _allowed(scope.allowed_selectors, selector.key):
            raise AuthorizationError("selector use is outside authorization scope")
    for atom in (*plan.edges, *plan.filters, *(x for x in plan.projections if isinstance(x, FieldProjection))):
        if not _allowed(scope.allowed_properties, atom.property_key):
            raise AuthorizationError("property operation is outside authorization scope")
    if scope.allowed_graphs is not None:
        if not dataset.graph_iris or not set(dataset.graph_iris) <= scope.allowed_graphs:
            raise AuthorizationError("dataset graph scope is not authorized")


def _triples(
    graph: Graph | Dataset,
    pattern: tuple[Any, Any, Any],
    graph_iris: tuple[str, ...],
) -> Iterable[tuple[Any, Any, Any]]:
    if graph_iris:
        if not isinstance(graph, Dataset):
            raise EvidenceError("named graph scope requires an RDFLib Dataset")
        for graph_iri in graph_iris:
            yield from graph.graph(URIRef(graph_iri)).triples(pattern)
        return
    yield from graph.triples(pattern)


def _physical_triple(
    graph: Graph | Dataset,
    source: Term,
    prop: PropertyDef,
    target: Term,
    graph_iris: tuple[str, ...],
) -> tuple[Term, str, Term]:
    subject, object_ = (target.rdf(), source.rdf()) if prop.inverse else (source.rdf(), target.rdf())
    for s, p, o in _triples(graph, (subject, URIRef(prop.predicate_iri), object_), graph_iris):
        return Term.from_rdf(s), str(p), Term.from_rdf(o)
    raise EvidenceError("row lacks required physical triple witness")


def _evidence_id(execution: str, atom: str, triple: tuple[Term, str, Term]) -> str:
    return _digest("triple-evidence", {"execution": execution, "atom": atom, "triple": [asdict(triple[0]), triple[1], asdict(triple[2])]})


def _certificate(
    plan: Plan,
    catalog: Catalog,
    graph: Graph | Dataset,
    compiled: CompiledQuery,
    execution_id: str,
    row: ResultRow,
    dataset_scope: DatasetScope,
) -> tuple[RowSupportCertificate, tuple[TriplePatternMatchEvidence, ...]]:
    properties = {x.key: x for x in catalog.properties}
    selectors = {x.key: x for x in catalog.selectors}
    lenses = {x.id: x for x in plan.lenses}
    bindings = {x.entity_id: x.term for x in row.entity_bindings}
    evidence: list[TriplePatternMatchEvidence] = []
    supports: list[PlanAtomSupport] = []

    def witnessed(atom_id: str, atom_kind: str, triple: tuple[Term, str, Term]) -> None:
        identifier = _evidence_id(execution_id, atom_id, triple)
        evidence.append(TriplePatternMatchEvidence(identifier, execution_id, atom_id, *triple))
        supports.append(PlanAtomSupport(atom_kind, atom_id, "witnessed", (identifier,)))

    for use in plan.selectors:
        selector, term = selectors[use.key], bindings[use.entity]
        if term.value in selector.target_iris:
            supports.append(PlanAtomSupport("selector", use.id, "derived", derived_from_entity_ids=(use.entity,)))
        else:
            match = next(
                (
                    (Term.from_rdf(s), str(p), Term.from_rdf(o))
                    for s, p, o in _triples(graph, (term.rdf(), RDF.type, None), dataset_scope.graph_iris)
                    if str(o) in selector.classes
                ),
                None,
            )
            if match is None:
                raise EvidenceError("selector has no compatible witness")
            witnessed(use.id, "selector", match)
    for edge in plan.edges:
        source = bindings[lenses[edge.source_lens].entity]
        target = bindings[edge.target_entity]
        prop = properties[edge.property_key]
        triples = [_physical_triple(graph, source, prop, target, dataset_scope.graph_iris)]
        branch = next(x for x in prop.branches if x.key == edge.branch_key)
        triples.extend(
            next(
                (Term.from_rdf(s), str(p), Term.from_rdf(o))
                for s, p, o in _triples(graph, (target.rdf(), RDF.type, URIRef(class_iri)), dataset_scope.graph_iris)
            )
            for class_iri in branch.classes
        )
        identifiers = []
        for triple in triples:
            identifier = _evidence_id(execution_id, edge.id, triple)
            identifiers.append(identifier)
            evidence.append(TriplePatternMatchEvidence(identifier, execution_id, edge.id, *triple))
        supports.append(PlanAtomSupport("edge", edge.id, "witnessed", tuple(identifiers)))
    for expression in plan.filters:
        source = bindings[lenses[expression.lens].entity]
        prop = properties[expression.property_key]
        if isinstance(expression, Eq):
            target = expression.value
        else:
            triples = (
                _triples(graph, (None, URIRef(prop.predicate_iri), source.rdf()), dataset_scope.graph_iris)
                if prop.inverse
                else _triples(graph, (source.rdf(), URIRef(prop.predicate_iri), None), dataset_scope.graph_iris)
            )
            triple = next(triples, None)
            if triple is None:
                raise EvidenceError("existence filter has no witness")
            target = Term.from_rdf(triple[0] if prop.inverse else triple[2])
        triples = [_physical_triple(graph, source, prop, target, dataset_scope.graph_iris)]
        if isinstance(expression, Eq):
            branch = next(x for x in prop.branches if x.key == expression.branch_key)
            triples.extend(
                next(
                    (Term.from_rdf(s), str(p), Term.from_rdf(o))
                    for s, p, o in _triples(
                        graph,
                        (target.rdf(), RDF.type, URIRef(class_iri)),
                        dataset_scope.graph_iris,
                    )
                )
                for class_iri in branch.classes
            )
        identifiers = []
        for triple in triples:
            identifier = _evidence_id(execution_id, expression.id, triple)
            identifiers.append(identifier)
            evidence.append(TriplePatternMatchEvidence(identifier, execution_id, expression.id, *triple))
        supports.append(PlanAtomSupport("filter", expression.id, "derived", tuple(identifiers)))
    for index, projection in enumerate(plan.projections):
        value = row.values[index]
        if isinstance(projection, NodeProjection):
            supports.append(PlanAtomSupport("projection", projection.id, "derived", derived_from_entity_ids=(projection.entity,)))
        elif value is None:
            if projection.required:
                raise EvidenceError("required projection is unbound")
            supports.append(PlanAtomSupport("projection", projection.id, "optional_unbound"))
        else:
            source = bindings[lenses[projection.lens].entity]
            prop = properties[projection.property_key]
            branch = next(x for x in prop.branches if x.key == projection.branch_key)
            triples = [
                _physical_triple(
                    graph,
                    source,
                    prop,
                    value,
                    dataset_scope.graph_iris,
                )
            ]
            triples.extend(
                next(
                    (Term.from_rdf(s), str(p), Term.from_rdf(o))
                    for s, p, o in _triples(
                        graph,
                        (value.rdf(), RDF.type, URIRef(class_iri)),
                        dataset_scope.graph_iris,
                    )
                )
                for class_iri in branch.classes
            )
            identifiers = []
            for triple in triples:
                identifier = _evidence_id(execution_id, projection.id, triple)
                identifiers.append(identifier)
                evidence.append(
                    TriplePatternMatchEvidence(
                        identifier,
                        execution_id,
                        projection.id,
                        *triple,
                    )
                )
            supports.append(
                PlanAtomSupport(
                    "projection",
                    projection.id,
                    "witnessed",
                    tuple(identifiers),
                )
            )
    expected = compiled.atom_ids
    actual = tuple(x.atom_id for x in supports)
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise EvidenceError("certificate does not cover the complete Row Atom Set exactly once")
    certificate_id = _digest(
        "row-certificate",
        {
            "execution": execution_id,
            "plan": compiled.plan_digest,
            "query": compiled.digest,
            "row": row.key,
            "supports": [asdict(x) for x in supports],
        },
    )
    return (
        RowSupportCertificate(certificate_id, execution_id, compiled.plan_digest, compiled.digest, row.key, row.entity_bindings, tuple(supports)),
        tuple(evidence),
    )


def validate_evidence(
    plan: Plan,
    compiled: CompiledQuery,
    packet: EvidencePacket,
    rows: Sequence[ResultRow],
    *,
    catalog: Catalog,
    data: Graph | Dataset,
    policy: QueryPolicy | None = None,
) -> None:
    try:
        expected_compiled = compile_plan(
            plan,
            catalog,
            limit=compiled.ast.limit,
            policy=policy or QueryPolicy(),
            graph_iris=packet.dataset_scope.graph_iris,
        )
    except Exception as exc:
        raise EvidenceError("compiled query cannot be derived from its plan") from exc
    if compiled != expected_compiled:
        raise EvidenceError("compiled query does not match its plan")
    query_items = [x for x in packet.evidence if isinstance(x, QueryResultEvidence)]
    if len(query_items) != 1:
        raise EvidenceError("packet requires exactly one QueryResultEvidence")
    query = query_items[0]
    evidence_ids = [x.id for x in packet.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise EvidenceError("evidence IDs must be unique")
    expected_query_id = _digest(
        "query-result-evidence",
        {
            "execution": query.execution_id,
            "query": query.query_digest,
            "complete": query.completed,
            "kind": query.result_kind,
            "rows": query.row_count,
            "boolean": query.boolean_value,
            "more": query.more_results,
        },
    )
    common = (
        query.id == expected_query_id
        and packet.execution_id == query.execution_id
        and packet.catalog_revision == catalog.revision == plan.catalog_revision
        and plan_digest(plan) == compiled.plan_digest
        and packet.plan_digest == compiled.plan_digest == query.plan_digest
        and packet.query_digest == compiled.digest == query.query_digest
        and packet.dataset_scope.digest == query.dataset_scope_digest
        and packet.authorization_scope_digest == query.authorization_scope_digest
        and packet.execution_complete == query.completed
        and compiled.ast.dataset_graphs == tuple(sorted(packet.dataset_scope.graph_iris))
    )
    if not common:
        raise EvidenceError("evidence scope or completion contradiction")
    if any(getattr(item, "execution_id", None) != packet.execution_id for item in packet.evidence):
        raise EvidenceError("mixed-execution evidence")
    if query.result_kind != ("failed" if not query.completed else plan.kind):
        raise EvidenceError("query result kind contradicts the plan")
    if plan.kind == "select" and query.completed and (
        query.boolean_value is not None or query.row_count != len(rows)
    ):
        raise EvidenceError("SELECT evidence contradicts its rows")
    if plan.kind == "ask" and query.completed and (
        query.boolean_value is None or query.row_count != 0 or query.more_results or rows
    ):
        raise EvidenceError("ASK evidence contradicts its Boolean")
    expected_completeness = (
        "unknown"
        if not query.completed
        else "incomplete"
        if query.more_results
        else "complete"
    )
    if packet.result_set_completeness != expected_completeness:
        raise EvidenceError("packet completeness contradicts query evidence")
    expected_atoms = set(compiled.atom_ids)
    certificates = {x.row_key: x for x in packet.certificates}
    row_evidence = [x for x in packet.evidence if isinstance(x, RowEvidence)]
    triple_evidence = {
        x.id: x for x in packet.evidence if isinstance(x, TriplePatternMatchEvidence)
    }
    if any(
        item.id != _evidence_id(
            packet.execution_id,
            item.atom_id,
            (item.subject, item.predicate, item.object),
        )
        or item.assertion_status != "unknown"
        or not any(
            True
            for _ in _triples(
                data,
                (item.subject.rdf(), URIRef(item.predicate), item.object.rdf()),
                packet.dataset_scope.graph_iris,
            )
        )
        for item in triple_evidence.values()
    ):
        raise EvidenceError("invalid triple evidence identity or assertion status")
    if len({row.key for row in rows}) != len(rows):
        raise EvidenceError("row keys must be unique")
    properties = {x.key: x for x in catalog.properties}
    selectors = {x.key: x for x in catalog.selectors}
    lenses = {x.id: x for x in plan.lenses}
    atom_by_id = {
        item.id: item
        for item in (*plan.selectors, *plan.edges, *plan.filters, *plan.projections)
    }
    referenced_evidence: set[str] = set()

    def matches_property(
        item: TriplePatternMatchEvidence,
        prop: PropertyDef,
        source: Term,
        target: Term,
    ) -> bool:
        subject, object_ = (target, source) if prop.inverse else (source, target)
        return (
            item.subject == subject
            and item.predicate == prop.predicate_iri
            and item.object == object_
        )

    if rows:
        if any(
            len(row.values) != len(plan.projections)
            or len(row.entity_bindings) != len(plan.entities)
            for row in rows
        ):
            raise EvidenceError("row arity contradicts the plan")
        if (
            len(packet.certificates) != len(rows)
            or len(certificates) != len(rows)
            or len({x.id for x in packet.certificates}) != len(rows)
            or len(row_evidence) != len(rows)
        ):
            raise EvidenceError("every positive row requires one certificate and RowEvidence")
        for row in rows:
            expected_row_key = _digest(
                "row",
                {
                    "values": [asdict(x) if x else None for x in row.values],
                    "bindings": [asdict(x) for x in row.entity_bindings],
                },
            )
            if row.key != expected_row_key:
                raise EvidenceError("row identity mismatch")
            certificate = certificates.get(row.key)
            if (
                certificate is None
                or certificate.execution_id != packet.execution_id
                or certificate.plan_digest != compiled.plan_digest
                or certificate.query_digest != compiled.digest
                or certificate.entity_bindings != row.entity_bindings
            ):
                raise EvidenceError("certificate row binding mismatch")
            expected_certificate_id = _digest(
                "row-certificate",
                {
                    "execution": packet.execution_id,
                    "plan": compiled.plan_digest,
                    "query": compiled.digest,
                    "row": row.key,
                    "supports": [asdict(x) for x in certificate.plan_atom_support],
                },
            )
            if certificate.id != expected_certificate_id:
                raise EvidenceError("certificate identity mismatch")
            matching_row_evidence = [x for x in row_evidence if x.row_key == row.key]
            if len(matching_row_evidence) != 1:
                raise EvidenceError("row evidence mapping is not exact")
            row_item = matching_row_evidence[0]
            if (
                row_item.certificate_id != certificate.id
                or row_item.id
                != _digest(
                    "row-evidence",
                    {"execution": packet.execution_id, "row": row.key},
                )
            ):
                raise EvidenceError("row evidence identity mismatch")
            atom_ids = [x.atom_id for x in certificate.plan_atom_support]
            if set(atom_ids) != expected_atoms or len(atom_ids) != len(expected_atoms):
                raise EvidenceError("certificate atom coverage contradiction")
            bindings = {x.entity_id: x.term for x in row.entity_bindings}
            if set(bindings) != {x.id for x in plan.entities}:
                raise EvidenceError("certificate entity binding coverage mismatch")
            for support in certificate.plan_atom_support:
                atom = atom_by_id[support.atom_id]
                if len(support.evidence_ids) != len(set(support.evidence_ids)):
                    raise EvidenceError("support evidence IDs must be unique")
                if len(support.derived_from_entity_ids) != len(set(support.derived_from_entity_ids)):
                    raise EvidenceError("support entity derivations must be unique")
                items = []
                for evidence_id in support.evidence_ids:
                    if evidence_id not in triple_evidence:
                        raise EvidenceError("support evidence is missing, duplicated, or incompatible")
                    item = triple_evidence[evidence_id]
                    if item.atom_id != support.atom_id:
                        raise EvidenceError("support references evidence for another atom")
                    referenced_evidence.add(evidence_id)
                    items.append(item)
                if support.status == "witnessed" and (not support.evidence_ids or support.derived_from_entity_ids):
                    raise EvidenceError("invalid witnessed support")
                if support.status == "derived" and not (support.evidence_ids or support.derived_from_entity_ids):
                    raise EvidenceError("invalid derived support")
                if support.status == "optional_unbound" and (support.evidence_ids or support.derived_from_entity_ids):
                    raise EvidenceError("invalid optional-unbound support")
                if support.status not in {"witnessed", "derived", "optional_unbound"}:
                    raise EvidenceError("illegal support status")
                if isinstance(atom, SelectorUse):
                    selector, term = selectors[atom.key], bindings[atom.entity]
                    if term.value in selector.target_iris:
                        valid = support.status == "derived" and support.derived_from_entity_ids == (atom.entity,) and not items
                    else:
                        valid = support.status == "witnessed" and any(
                            item.subject == term
                            and item.predicate == str(RDF.type)
                            and item.object.kind == "iri"
                            and item.object.value in selector.classes
                            for item in items
                        )
                elif isinstance(atom, Edge):
                    prop = properties[atom.property_key]
                    source, target = bindings[lenses[atom.source_lens].entity], bindings[atom.target_entity]
                    branch = next(x for x in prop.branches if x.key == atom.branch_key)
                    valid = support.status == "witnessed" and any(
                        matches_property(item, prop, source, target) for item in items
                    ) and all(
                        any(
                            item.subject == target
                            and item.predicate == str(RDF.type)
                            and item.object == Term("iri", class_iri)
                            for item in items
                        )
                        for class_iri in branch.classes
                    )
                elif isinstance(atom, (Eq, Exists)):
                    prop = properties[atom.property_key]
                    source = bindings[lenses[atom.lens].entity]
                    valid = support.status == "derived" and any(
                        matches_property(item, prop, source, atom.value)
                        if isinstance(atom, Eq)
                        else (
                            item.object == source
                            if prop.inverse
                            else item.subject == source
                        )
                        and item.predicate == prop.predicate_iri
                        for item in items
                    )
                    if isinstance(atom, Eq):
                        branch = next(x for x in prop.branches if x.key == atom.branch_key)
                        valid = valid and all(
                            any(
                                item.subject == atom.value
                                and item.predicate == str(RDF.type)
                                and item.object == Term("iri", class_iri)
                                for item in items
                            )
                            for class_iri in branch.classes
                        )
                elif isinstance(atom, NodeProjection):
                    valid = support.status == "derived" and support.derived_from_entity_ids == (atom.entity,) and not items
                else:
                    index = next(i for i, projection in enumerate(plan.projections) if projection.id == atom.id)
                    value = row.values[index]
                    if value is None:
                        valid = not atom.required and support.status == "optional_unbound" and not items
                    else:
                        prop = properties[atom.property_key]
                        source = bindings[lenses[atom.lens].entity]
                        branch = next(x for x in prop.branches if x.key == atom.branch_key)
                        valid = support.status == "witnessed" and any(
                            matches_property(item, prop, source, value) for item in items
                        ) and all(
                            any(
                                item.subject == value
                                and item.predicate == str(RDF.type)
                                and item.object == Term("iri", class_iri)
                                for item in items
                            )
                            for class_iri in branch.classes
                        )
                if not valid:
                    raise EvidenceError("support is incompatible with its atom or row")
    elif packet.certificates or row_evidence:
        raise EvidenceError("empty or Boolean results cannot carry row certificates")
    if set(triple_evidence) != referenced_evidence:
        raise EvidenceError("packet contains unreferenced triple evidence")
    if packet.execution_complete and packet.result_set_completeness not in {"complete", "incomplete"}:
        raise EvidenceError("completed result has contradictory completeness")
    if packet.execution_complete != packet.result_extent_satisfied:
        raise EvidenceError("execution and requested-extent status contradict")
    if not packet.execution_complete and (
        packet.result_extent_satisfied or packet.result_set_completeness == "complete"
    ):
        raise EvidenceError("interrupted result cannot claim completion")


class ShapeQueryEngine:
    def __init__(
        self,
        *,
        data: Graph | Dataset,
        catalog: Catalog,
        authorization: AuthorizationScope,
        dataset_scope: DatasetScope,
        policy: QueryPolicy | None = None,
    ) -> None:
        if (
            not isinstance(catalog, Catalog)
            or not isinstance(authorization, AuthorizationScope)
            or not isinstance(dataset_scope, DatasetScope)
            or (policy is not None and not isinstance(policy, QueryPolicy))
        ):
            raise PolicyError("typed catalog, authorization, dataset scope, and query policy required")
        if dataset_scope.default_graph_mode != "store_default":
            raise PolicyError("version 0.1 supports only the declared RDFLib store-default graph mode")
        if dataset_scope.graph_iris and not isinstance(data, Dataset):
            raise PolicyError("named graph scopes require an RDFLib Dataset")
        self.data = data
        self.catalog = catalog
        self.authorization = authorization
        self.dataset_scope = dataset_scope
        self.policy = policy or QueryPolicy()

    @classmethod
    def from_rdflib(
        cls,
        *,
        data: Graph | Dataset,
        sources: Iterable[ShapeSource],
        authorization: AuthorizationScope,
        dataset_scope: DatasetScope | None = None,
        overlays: Iterable[ApplicationOverlay] = (),
        policy: QueryPolicy | None = None,
        catalog_policy: CatalogPolicy | None = None,
        build_id: str | None = None,
    ) -> "ShapeQueryEngine":
        catalog = Catalog.build(sources, overlays=overlays, policy=catalog_policy, build_id=build_id)
        return cls(
            data=data,
            catalog=catalog,
            authorization=authorization,
            dataset_scope=dataset_scope or DatasetScope("local"),
            policy=policy,
        )

    def validate_plan(self, raw: Mapping[str, Any] | Plan) -> Plan:
        plan = raw if isinstance(raw, Plan) else normalize_plan(raw, self.catalog, self.policy)
        _validate_plan(plan, self.catalog, self.policy)
        _authorize(plan, self.catalog, self.authorization, self.dataset_scope)
        return _canonical_plan(plan)

    def compile(self, plan: Plan, *, limit: int | None = None) -> CompiledQuery:
        return compile_plan(
            self.validate_plan(plan),
            self.catalog,
            limit=limit,
            policy=self.policy,
            graph_iris=self.dataset_scope.graph_iris,
        )

    def explain_plan(self, raw: Mapping[str, Any] | Plan) -> PlanExplanation:
        plan = self.validate_plan(raw)
        compiled = compile_plan(
            plan,
            self.catalog,
            policy=self.policy,
            graph_iris=self.dataset_scope.graph_iris,
        )
        return PlanExplanation(
            self.catalog.revision,
            compiled.plan_digest,
            self.authorization.digest,
            self.policy.revision,
            tuple(x.id for x in plan.entities),
            tuple(x.id for x in plan.selectors),
            tuple(x.id for x in plan.lenses),
            compiled.atom_ids,
            compiled.text,
            self.catalog.diagnostics,
        )

    def execute_plan(
        self,
        raw: Mapping[str, Any] | Plan,
        *,
        request: ExecutionRequest | None = None,
    ) -> QueryOutcome:
        if request is None:
            request = ExecutionRequest.complete()
        elif not isinstance(request, ExecutionRequest):
            return Unsupported("unsupported", "execution request must be typed")
        try:
            plan = self.validate_plan(raw)
        except AuthorizationError as exc:
            return PolicyLimited("policy_limited", str(exc))
        except PolicyError as exc:
            return PolicyLimited("policy_limited", str(exc))
        except (UnsupportedPlan, PlanError) as exc:
            return Unsupported("unsupported", str(exc))
        if request.extent not in {"complete", "examples"}:
            return Unsupported("unsupported", "unsupported result extent")
        if request.cancelled:
            return Failed("failed", "cancelled")
        requested = request.count if request.extent == "examples" else self.policy.max_result_rows
        if requested is None or requested > self.policy.max_result_rows:
            return PolicyLimited("policy_limited", "requested result extent exceeds policy")
        limit = requested + 1 if plan.kind == "select" else None
        try:
            compiled = compile_plan(
                plan,
                self.catalog,
                limit=limit,
                policy=self.policy,
                graph_iris=self.dataset_scope.graph_iris,
            )
        except PolicyError as exc:
            return PolicyLimited("policy_limited", str(exc))
        except Exception as exc:
            return Failed("failed", f"compilation_failed:{type(exc).__name__}")
        execution_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            raw_result = self.data.query(compiled.text)
            if time.monotonic() - started > self.policy.deadline_seconds:
                return self._failed_packet(plan, compiled, request, execution_id, "deadline_exceeded")
            if plan.kind == "ask":
                if getattr(raw_result, "type", None) != "ASK" or type(getattr(raw_result, "askAnswer", None)) is not bool:
                    raise EvidenceError("malformed ASK result envelope")
                return self._boolean_outcome(plan, compiled, request, execution_id, raw_result.askAnswer)
            if getattr(raw_result, "type", None) != "SELECT":
                raise EvidenceError("malformed SELECT result envelope")
            return self._select_outcome(plan, compiled, request, execution_id, tuple(raw_result), requested)
        except Exception as exc:
            return self._failed_packet(plan, compiled, request, execution_id, f"execution_failed:{type(exc).__name__}")

    def _query_evidence(
        self,
        compiled: CompiledQuery,
        execution_id: str,
        *,
        completed: bool,
        result_kind: str,
        row_count: int = 0,
        boolean_value: bool | None = None,
        more_results: bool = False,
    ) -> QueryResultEvidence:
        identifier = _digest(
            "query-result-evidence",
            {
                "execution": execution_id,
                "query": compiled.digest,
                "complete": completed,
                "kind": result_kind,
                "rows": row_count,
                "boolean": boolean_value,
                "more": more_results,
            },
        )
        return QueryResultEvidence(
            identifier,
            execution_id,
            compiled.plan_digest,
            compiled.digest,
            self.dataset_scope.digest,
            self.authorization.digest,
            completed,
            result_kind,
            row_count,
            boolean_value,
            more_results,
        )

    def _packet(
        self,
        compiled: CompiledQuery,
        request: ExecutionRequest,
        execution_id: str,
        evidence: Sequence[EvidenceItem],
        certificates: Sequence[RowSupportCertificate],
        *,
        complete: bool,
        extent_satisfied: bool,
        completeness: str,
    ) -> EvidencePacket:
        return EvidencePacket(
            execution_id,
            self.catalog.revision,
            self.policy.revision,
            self.authorization.digest,
            self.dataset_scope,
            compiled.plan_digest,
            request.digest,
            compiled.digest,
            tuple(evidence),
            tuple(certificates),
            complete,
            extent_satisfied,
            completeness,
        )

    def _failed_packet(
        self,
        plan: Plan,
        compiled: CompiledQuery,
        request: ExecutionRequest,
        execution_id: str,
        reason: str,
    ) -> Failed:
        query = self._query_evidence(compiled, execution_id, completed=False, result_kind="failed")
        packet = self._packet(
            compiled,
            request,
            execution_id,
            (query,),
            (),
            complete=False,
            extent_satisfied=False,
            completeness="unknown",
        )
        validate_evidence(
            plan,
            compiled,
            packet,
            (),
            catalog=self.catalog,
            data=self.data,
            policy=self.policy,
        )
        return Failed("failed", reason, packet)

    def _boolean_outcome(
        self,
        plan: Plan,
        compiled: CompiledQuery,
        request: ExecutionRequest,
        execution_id: str,
        value: bool,
    ) -> QueryOutcome:
        query = self._query_evidence(
            compiled,
            execution_id,
            completed=True,
            result_kind="ask",
            boolean_value=value,
        )
        packet = self._packet(
            compiled,
            request,
            execution_id,
            (query,),
            (),
            complete=True,
            extent_satisfied=True,
            completeness="complete",
        )
        validate_evidence(
            plan,
            compiled,
            packet,
            (),
            catalog=self.catalog,
            data=self.data,
            policy=self.policy,
        )
        if value:
            return BooleanResult("boolean_result", True, packet)
        return NoMatch("no_match", self._no_match_message(), packet)

    def _select_outcome(
        self,
        plan: Plan,
        compiled: CompiledQuery,
        request: ExecutionRequest,
        execution_id: str,
        raw_rows: tuple[Any, ...],
        requested: int,
    ) -> QueryOutcome:
        more = len(raw_rows) > requested
        if request.extent == "complete" and more:
            return PolicyLimited("policy_limited", "complete result exceeds row policy")
        raw_rows = raw_rows[:requested]
        public_indexes = [compiled.ast.projections.index(name) for name in compiled.public_variables]
        entity_indexes = [(entity, compiled.ast.projections.index(variable)) for entity, variable in compiled.entity_variables]
        rows: list[ResultRow] = []
        try:
            for raw in raw_rows:
                values = tuple(Term.from_rdf(raw[index]) if raw[index] is not None else None for index in public_indexes)
                bindings = tuple(EntityBindingEvidence(entity, Term.from_rdf(raw[index])) for entity, index in entity_indexes)
                if any(binding.term.kind != "iri" for binding in bindings):
                    raise EvidenceError("entity result must be an IRI")
                row_key = _digest(
                    "row",
                    {
                        "values": [asdict(x) if x else None for x in values],
                        "bindings": [asdict(x) for x in bindings],
                    },
                )
                row = ResultRow(row_key, values, bindings)
                self._validate_row_contracts(plan, row)
                rows.append(row)
            rows.sort(key=lambda row: tuple(x.sort_key() if x else ("", "", "", "") for x in row.values) + tuple(x.term.sort_key() for x in row.entity_bindings))
            encoded = json.dumps([asdict(row) for row in rows], sort_keys=True).encode()
            if len(encoded) > self.policy.max_result_bytes:
                return self._failed_packet(plan, compiled, request, execution_id, "result_byte_limit")
            certificates: list[RowSupportCertificate] = []
            evidence: list[EvidenceItem] = []
            for row in rows:
                certificate, triples = _certificate(
                    plan,
                    self.catalog,
                    self.data,
                    compiled,
                    execution_id,
                    row,
                    self.dataset_scope,
                )
                certificates.append(certificate)
                evidence.extend(triples)
                evidence.append(RowEvidence(_digest("row-evidence", {"execution": execution_id, "row": row.key}), execution_id, row.key, certificate.id))
            evidence = list({item.id: item for item in evidence}.values())
            query = self._query_evidence(
                compiled,
                execution_id,
                completed=True,
                result_kind="select",
                row_count=len(rows),
                more_results=more,
            )
            packet = self._packet(
                compiled,
                request,
                execution_id,
                (query, *evidence),
                certificates,
                complete=True,
                extent_satisfied=True,
                completeness="incomplete" if more else "complete",
            )
            validate_evidence(
                plan,
                compiled,
                packet,
                rows,
                catalog=self.catalog,
                data=self.data,
                policy=self.policy,
            )
            if not rows:
                return NoMatch("no_match", self._no_match_message(), packet)
            return Selected("selected", tuple(rows), packet)
        except Exception as exc:
            return self._failed_packet(plan, compiled, request, execution_id, f"result_validation_failed:{type(exc).__name__}")

    def _validate_row_contracts(self, plan: Plan, row: ResultRow) -> None:
        properties = {x.key: x for x in self.catalog.properties}
        lenses = {x.id: x for x in plan.lenses}
        bindings = {x.entity_id: x.term for x in row.entity_bindings}
        for index, projection in enumerate(plan.projections):
            if not isinstance(projection, FieldProjection) or row.values[index] is None:
                continue
            prop = properties[projection.property_key]
            branch = next(x for x in prop.branches if x.key == projection.branch_key)
            if not branch.accepts(row.values[index]):
                raise EvidenceError("projected value violates its contract branch")
            if any(
                not any(
                    True
                    for _ in _triples(
                        self.data,
                        (row.values[index].rdf(), RDF.type, URIRef(class_iri)),
                        self.dataset_scope.graph_iris,
                    )
                )
                for class_iri in branch.classes
            ):
                raise EvidenceError("projected IRI violates its class contract")
            source = bindings[lenses[projection.lens].entity]
            triples = (
                _triples(self.data, (None, URIRef(prop.predicate_iri), source.rdf()), self.dataset_scope.graph_iris)
                if prop.inverse
                else _triples(self.data, (source.rdf(), URIRef(prop.predicate_iri), None), self.dataset_scope.graph_iris)
            )
            values = {
                Term.from_rdf(triple[0] if prop.inverse else triple[2])
                for triple in triples
            }
            if len(values) > 1:
                raise EvidenceError("scalar projection contract was violated by multiple values")

    def _no_match_message(self) -> str:
        return (
            f"No visible solution matched in dataset scope '{self.dataset_scope.dataset_id}' "
            f"within authorization scope '{self.authorization.scope_id}'."
        )


def render_result(outcome: QueryOutcome) -> str:
    if isinstance(outcome, Selected):
        lines = ["\t".join("" if value is None else value.sparql() for value in row.values) for row in outcome.rows]
        if outcome.packet.result_set_completeness == "incomplete":
            lines.append("[truncated: more visible matches exist]")
        return "\n".join(lines)
    if isinstance(outcome, BooleanResult):
        return "A visible solution matched the validated query."
    if isinstance(outcome, NoMatch):
        return outcome.message
    if isinstance(outcome, PolicyLimited):
        return f"Policy limited: {outcome.reason}"
    if isinstance(outcome, Unsupported):
        return f"Unsupported: {outcome.reason}"
    return f"Failed: {outcome.reason}"


__all__ = [
    "ApplicationOverlay",
    "AuthorizationScope",
    "BooleanResult",
    "Catalog",
    "CatalogError",
    "CatalogPolicy",
    "DatasetScope",
    "EvidenceError",
    "EvidencePacket",
    "ExecutionRequest",
    "Failed",
    "NoMatch",
    "Plan",
    "PlanError",
    "PlanExplanation",
    "PolicyLimited",
    "QualificationRecord",
    "QueryOutcome",
    "QueryPolicy",
    "RowSupportCertificate",
    "Selected",
    "SemanticQualification",
    "ShapeQueryEngine",
    "ShapeSource",
    "Term",
    "Unsupported",
    "compile_plan",
    "normalize_plan",
    "plan_digest",
    "render_ast",
    "render_result",
    "validate_evidence",
]
