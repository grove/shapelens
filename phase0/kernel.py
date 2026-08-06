"""Phase 0-only, fail-closed SHACL-to-SPARQL semantic kernel."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import rdflib
from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH


# Exact RDF-term identity requires preserving source lexical forms.
rdflib.NORMALIZE_LITERALS = False


class PlanError(ValueError):
    pass


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _iri(value: str) -> str:
    if not isinstance(value, str) or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\"{}|^`\\]+$", value):
        raise PlanError("absolute IRI required")
    return value


@dataclass(frozen=True)
class Term:
    kind: str
    value: str
    datatype: str | None = None
    language: str | None = None

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "Term":
        if not isinstance(raw, dict):
            raise PlanError("RDF term must be an object")
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
            if not isinstance(language, str) or not re.match(r"^[A-Za-z]+(?:-[A-Za-z0-9]+)*$", language):
                raise PlanError("valid language tag required")
            language = language.lower()
        return cls(kind, value, datatype, language)

    def rdf(self) -> URIRef | Literal:
        return URIRef(self.value) if self.kind == "iri" else Literal(self.value, datatype=URIRef(self.datatype) if self.datatype else None, lang=self.language)

    def sparql(self) -> str:
        if self.kind == "iri":
            return f"<{self.value}>"
        text = self.value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t").replace("\b", "\\b").replace("\n", "\\n").replace("\r", "\\r").replace("\f", "\\f")
        return f'"{text}"@{self.language}' if self.language else (f'"{text}"^^<{self.datatype}>' if self.datatype else f'"{text}"')


@dataclass(frozen=True)
class Entity: id: str; bound: Term | None
@dataclass(frozen=True)
class SelectorUse: id: str; entity: str; key: str
@dataclass(frozen=True)
class LensUse: id: str; entity: str; key: str
@dataclass(frozen=True)
class Edge: id: str; source_lens: str; property_key: str; branch_key: str; target_entity: str
@dataclass(frozen=True)
class Eq: id: str; lens: str; property_key: str; branch_key: str; value: Term
@dataclass(frozen=True)
class Exists: id: str; lens: str; property_key: str
@dataclass(frozen=True)
class NodeProjection: id: str; entity: str
@dataclass(frozen=True)
class FieldProjection: id: str; lens: str; property_key: str; branch_key: str; required: bool
@dataclass(frozen=True)
class Plan:
    kind: str; catalog_revision: str; entities: tuple[Entity, ...]; selectors: tuple[SelectorUse, ...]
    lenses: tuple[LensUse, ...]; edges: tuple[Edge, ...]; filters: tuple[Eq | Exists, ...]
    projections: tuple[NodeProjection | FieldProjection, ...]


@dataclass(frozen=True)
class LensDef: key: str; shape_term: str; trusted: bool = True; qualified: bool = True
@dataclass(frozen=True)
class SelectorDef: key: str; lens_key: str; kind: str; class_iri: str | None = None; target_iris: tuple[str, ...] = (); qualified: bool = True
@dataclass(frozen=True)
class PropertyDef: key: str; lens_key: str; source_term: str; predicate_iri: str; inverse: bool; branch_keys: tuple[str, ...]; scalar: bool; qualified: bool = True


@dataclass(frozen=True)
class Catalog:
    revision: str
    build_scope: str
    lenses: tuple[LensDef, ...]
    selectors: tuple[SelectorDef, ...]
    properties: tuple[PropertyDef, ...]

    @classmethod
    def build(
        cls,
        graphs: Iterable[Graph],
        *,
        build_id: str = "phase0",
        trusted: bool = True,
        qualified: bool = True,
        scalar_overrides: Iterable[tuple[str, str]] = (),
    ) -> "Catalog":
        # RDFLib's stored graph is the source of truth; keys are opaque and revision-scoped.
        graphs = tuple(graphs)
        rows: list[tuple[int, str, str, str]] = []
        for number, graph in enumerate(graphs):
            rows.extend((number, str(s), str(p), str(o)) for s, p, o in graph)
        seed = _digest({"build_id": build_id, "triples": sorted(rows)})
        overrides = set(scalar_overrides)
        lenses: list[LensDef] = []
        selectors: list[SelectorDef] = []
        props: list[PropertyDef] = []
        for graph in graphs:
            nodes = sorted(set(graph.subjects(RDF.type, SH.NodeShape)), key=str)
            for node in nodes:
                lens = f"{seed}:lens:{len(lenses)}"
                lenses.append(LensDef(lens, str(node), trusted, qualified))
                classes = sorted((str(x) for x in graph.objects(node, SH.targetClass) if isinstance(x, URIRef)))
                targets = sorted((str(x) for x in graph.objects(node, SH.targetNode) if isinstance(x, URIRef)))
                for class_iri in classes:
                    selectors.append(SelectorDef(f"{seed}:selector:{len(selectors)}", lens, "direct_type", class_iri, qualified=qualified))
                if targets:
                    selectors.append(SelectorDef(f"{seed}:selector:{len(selectors)}", lens, "target_nodes", target_iris=tuple(targets), qualified=qualified))
                for ps in sorted(graph.objects(node, SH.property), key=str):
                    paths = tuple(graph.objects(ps, SH.path))
                    if len(paths) != 1:
                        continue
                    path = paths[0]
                    inverse = False
                    if isinstance(path, BNode):
                        inverse_paths = tuple(graph.objects(path, SH.inversePath))
                        if len(inverse_paths) != 1:
                            continue
                        path, inverse = inverse_paths[0], True
                    if not isinstance(path, URIRef):
                        continue
                    branches = tuple(f"{seed}:branch:{len(props)}:{i}" for i, _ in enumerate(graph.objects(ps, SH['class'])) ) or (f"{seed}:branch:{len(props)}:0",)
                    scalar = graph.value(ps, SH.maxCount) == Literal(1) or (str(node), str(path)) in overrides
                    props.append(PropertyDef(f"{seed}:property:{len(props)}", lens, str(ps), str(path), inverse, branches, scalar, qualified))
        revision = _digest({
            "build_scope": seed,
            "lenses": [asdict(item) for item in lenses],
            "selectors": [asdict(item) for item in selectors],
            "properties": [asdict(item) for item in props],
        })
        return cls(revision, seed, tuple(lenses), tuple(selectors), tuple(props))

    def dump(self) -> dict[str, Any]: return asdict(self)
    @classmethod
    def reload(cls, raw: dict[str, Any]) -> "Catalog":
        lenses = tuple(LensDef(**item) for item in raw["lenses"])
        selectors = tuple(SelectorDef(**{**item, "target_iris": tuple(item["target_iris"])}) for item in raw["selectors"])
        properties = tuple(PropertyDef(**{**item, "branch_keys": tuple(item["branch_keys"])}) for item in raw["properties"])
        revision = _digest({
            "build_scope": raw["build_scope"],
            "lenses": [asdict(item) for item in lenses],
            "selectors": [asdict(item) for item in selectors],
            "properties": [asdict(item) for item in properties],
        })
        if raw.get("revision") != revision:
            raise PlanError("catalog artifact integrity failure")
        return cls(revision, raw["build_scope"], lenses, selectors, properties)


def _items(raw: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = raw.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value): raise PlanError(f"{name} must be an array of objects")
    return value


def _unique(items: Iterable[Any], label: str) -> None:
    values = [x.id for x in items]
    if len(values) != len(set(values)) or any(not isinstance(x, str) or not x for x in values): raise PlanError(f"unique {label} IDs required")


def normalize(raw: dict[str, Any], catalog: Catalog) -> Plan:
    if raw.get("kind") not in {"select", "ask"} or raw.get("catalog_revision") != catalog.revision: raise PlanError("kind or catalog revision invalid")
    entities = tuple(Entity(x["id"], Term.load(x["binding"]) if x.get("binding") else None) for x in _items(raw, "entities"))
    if any(e.bound and e.bound.kind != "iri" for e in entities): raise PlanError("entity binding must be IRI")
    selectors = tuple(SelectorUse(x["id"], x["entity"], x["key"]) for x in _items(raw, "selectors"))
    lenses = tuple(LensUse(x["id"], x["entity"], x["key"]) for x in _items(raw, "lenses"))
    edges = tuple(Edge(x["id"], x["source_lens"], x["property_key"], x["branch_key"], x["target_entity"]) for x in _items(raw, "edges"))
    filters: list[Eq | Exists] = []
    for x in _items(raw, "filters"):
        if x.get("kind") == "eq": filters.append(Eq(x["id"], x["lens"], x["property_key"], x["branch_key"], Term.load(x["value"])))
        elif x.get("kind") == "exists": filters.append(Exists(x["id"], x["lens"], x["property_key"]))
        else: raise PlanError("unsupported filter")
    projections: list[NodeProjection | FieldProjection] = []
    for x in _items(raw, "projections"):
        if x.get("kind") == "node": projections.append(NodeProjection(x["id"], x["entity"]))
        elif x.get("kind") == "field":
            if type(x.get("required")) is not bool: raise PlanError("field projection requires an explicit Boolean")
            projections.append(FieldProjection(x["id"], x["lens"], x["property_key"], x["branch_key"], x["required"]))
        else: raise PlanError("unsupported projection")
    plan = Plan(raw["kind"], catalog.revision, entities, selectors, lenses, edges, tuple(filters), tuple(projections))
    _validate(plan, catalog)
    return _canonical(plan)


def _validate(p: Plan, c: Catalog) -> None:
    _unique(p.entities, "entity"); _unique(p.selectors, "selector"); _unique(p.lenses, "lens"); _unique(p.edges, "edge"); _unique(p.filters, "filter"); _unique(p.projections, "projection")
    if p.kind == "select" and not p.projections or p.kind == "ask" and p.projections: raise PlanError("select needs projections; ask has none")
    entity = {x.id: x for x in p.entities}; lens = {x.id: x for x in p.lenses}; lens_def = {x.key: x for x in c.lenses}; prop = {x.key: x for x in c.properties}; selector = {x.key: x for x in c.selectors}
    if not entity or len({(x.entity, x.key) for x in p.lenses}) != len(p.lenses): raise PlanError("entities and unique lens uses required")
    for x in p.lenses:
        q = lens_def.get(x.key)
        if x.entity not in entity or q is None or not q.trusted or not q.qualified: raise PlanError("unknown, untrusted, or unqualified lens use")
    selected: set[str] = set()
    for x in p.selectors:
        q = selector.get(x.key)
        source = lens_def.get(q.lens_key) if q else None
        if x.entity not in entity or q is None or source is None or not source.trusted or not source.qualified or not q.qualified or x.entity in selected: raise PlanError("invalid selector use")
        selected.add(x.entity)
    used_lenses: set[str] = set(); incoming: set[str] = set(); adjacency: dict[str, set[str]] = {x.id: set() for x in p.entities}
    def check(lid: str, pk: str, branch: str | None = None) -> PropertyDef:
        if lid not in lens or pk not in prop or prop[pk].lens_key != lens[lid].key or not prop[pk].qualified: raise PlanError("unknown or unqualified property")
        q = prop[pk]
        if branch is not None and branch not in q.branch_keys: raise PlanError("unknown contract branch")
        used_lenses.add(lid); return q
    for x in p.edges:
        check(x.source_lens, x.property_key, x.branch_key)
        if x.target_entity not in entity: raise PlanError("unknown edge target")
        incoming.add(x.target_entity); adjacency[lens[x.source_lens].entity].add(x.target_entity); adjacency[x.target_entity].add(lens[x.source_lens].entity)
    for x in p.filters:
        check(x.lens, x.property_key, getattr(x, "branch_key", None))
    for x in p.projections:
        if isinstance(x, NodeProjection):
            if x.entity not in entity: raise PlanError("unknown projection entity")
        else:
            q = check(x.lens, x.property_key, x.branch_key)
            if not x.required or not q.scalar: raise PlanError("only required qualified scalar fields supported")
    semantic_groups = (
        [(x.entity, x.key) for x in p.selectors],
        [(x.source_lens, x.property_key, x.branch_key, x.target_entity) for x in p.edges],
        [(type(x).__name__, x.lens, x.property_key, getattr(x, "branch_key", None), json.dumps(asdict(getattr(x, "value", None)), sort_keys=True) if isinstance(x, Eq) else None) for x in p.filters],
        [(type(x).__name__, x.entity) if isinstance(x, NodeProjection) else (type(x).__name__, x.lens, x.property_key, x.branch_key, x.required) for x in p.projections],
    )
    if any(len(items) != len(set(items)) for items in semantic_groups): raise PlanError("duplicate semantic atom")
    if used_lenses != set(lens): raise PlanError("unused lens use")
    for e in p.entities:
        if e.bound is None and e.id not in incoming and e.id not in selected: raise PlanError("unbound root requires selector")
    if p.entities:
        seen, todo = set(), [p.entities[0].id]
        while todo:
            now = todo.pop()
            if now not in seen: seen.add(now); todo += list(adjacency[now] - seen)
        if len(p.entities) > 1 and seen != set(entity): raise PlanError("required edges must connect entities")


def _canonical(p: Plan) -> Plan:
    # Canonical local IDs make input ordering and caller names semantically irrelevant.
    lens_by_id = {x.id: x for x in p.lenses}
    def entity_signature(item: Entity) -> str:
        outgoing = sorted((edge.property_key, edge.branch_key) for edge in p.edges if lens_by_id[edge.source_lens].entity == item.id)
        incoming = sorted((edge.property_key, edge.branch_key) for edge in p.edges if edge.target_entity == item.id)
        return json.dumps({
            "bound": asdict(item.bound) if item.bound else None,
            "selectors": sorted(x.key for x in p.selectors if x.entity == item.id),
            "lenses": sorted(x.key for x in p.lenses if x.entity == item.id),
            "outgoing": outgoing,
            "incoming": incoming,
            "node_projection": any(isinstance(x, NodeProjection) and x.entity == item.id for x in p.projections),
        }, sort_keys=True)
    entities = sorted(p.entities, key=entity_signature); em = {x.id: f"e{i}" for i, x in enumerate(entities)}
    lenses = sorted(p.lenses, key=lambda x: (em[x.entity], x.key)); lm = {x.id: f"l{i}" for i, x in enumerate(lenses)}
    selectors = sorted(p.selectors, key=lambda x: (em[x.entity], x.key)); sm = {x.id: f"s{i}" for i, x in enumerate(selectors)}
    edges = sorted(p.edges, key=lambda x: (lm[x.source_lens], x.property_key, x.branch_key, em[x.target_entity]))
    filters = sorted(p.filters, key=lambda x: (
        x.__class__.__name__, lm[x.lens], x.property_key, getattr(x, "branch_key", ""),
        json.dumps(asdict(x.value), sort_keys=True) if isinstance(x, Eq) else "",
    ))
    projections = sorted(p.projections, key=lambda x: (
        x.__class__.__name__, em[x.entity] if isinstance(x, NodeProjection) else lm[x.lens],
        "" if isinstance(x, NodeProjection) else x.property_key,
        "" if isinstance(x, NodeProjection) else x.branch_key,
    ))
    return Plan(p.kind, p.catalog_revision, tuple(Entity(em[x.id], x.bound) for x in entities), tuple(SelectorUse(sm[x.id], em[x.entity], x.key) for x in selectors), tuple(LensUse(lm[x.id], em[x.entity], x.key) for x in lenses), tuple(Edge(f"a{i}", lm[x.source_lens], x.property_key, x.branch_key, em[x.target_entity]) for i, x in enumerate(edges)), tuple((Eq(f"f{i}", lm[x.lens], x.property_key, x.branch_key, x.value) if isinstance(x, Eq) else Exists(f"f{i}", lm[x.lens], x.property_key)) for i, x in enumerate(filters)), tuple((NodeProjection(f"p{i}", em[x.entity]) if isinstance(x, NodeProjection) else FieldProjection(f"p{i}", lm[x.lens], x.property_key, x.branch_key, x.required)) for i, x in enumerate(projections)))


def plan_digest(plan: Plan) -> str: return _digest(asdict(plan))


@dataclass(frozen=True)
class Compiled:
    query: str
    evidence_query: str | None
    plan_digest: str
    atom_ids: tuple[str, ...]
    public_count: int
    entity_columns: tuple[tuple[str, int], ...]


def compile_plan(plan: Plan, catalog: Catalog) -> Compiled:
    props = {x.key: x for x in catalog.properties}; sels = {x.key: x for x in catalog.selectors}; lenses = {x.id: x for x in plan.lenses}; lines: list[str] = []
    def variable(e: str) -> str: return "?" + e
    def pattern(source: str, q: PropertyDef, target: str) -> str: return f"{target} <{q.predicate_iri}> {source} ." if q.inverse else f"{source} <{q.predicate_iri}> {target} ."
    for e in plan.entities:
        if e.bound: lines.append(f"VALUES {variable(e.id)} {{ {e.bound.sparql()} }}")
    for s in plan.selectors:
        q = sels[s.key]; v = variable(s.entity)
        lines.append(f"{v} <{RDF.type}> <{q.class_iri}> ." if q.kind == "direct_type" else f"VALUES {v} {{ {' '.join(f'<{x}>' for x in q.target_iris)} }}")
    for e in plan.edges:
        lines.append(pattern(variable(lenses[e.source_lens].entity), props[e.property_key], variable(e.target_entity)))
    for i, f in enumerate(plan.filters):
        q, source, value = props[f.property_key], variable(lenses[f.lens].entity), f"?fv{i}"
        lines.append(pattern(source, q, value))
        if isinstance(f, Eq): lines.append(f"FILTER(sameTerm({value}, {f.value.sparql()}))")
    fields: list[str] = []
    for i, p in enumerate(plan.projections):
        if isinstance(p, NodeProjection): fields.append(variable(p.entity))
        else:
            v = f"?pv{i}"; lines.append(pattern(variable(lenses[p.lens].entity), props[p.property_key], v)); fields.append(v)
    body = "\n  ".join(lines)
    evidence_query = None
    entity_columns: list[tuple[str, int]] = []
    if plan.kind == "ask":
        query = f"ASK {{\n  {body}\n}}"
        evidence_fields = [variable(entity.id) for entity in plan.entities]
        evidence_query = f"SELECT DISTINCT {' '.join(evidence_fields)} WHERE {{\n  {body}\n}} LIMIT 1"
        entity_columns = [(entity.id, index) for index, entity in enumerate(plan.entities)]
    else:
        public_count = len(fields)
        evidence_fields = list(fields)
        for entity in plan.entities:
            name = variable(entity.id)
            if name not in evidence_fields:
                evidence_fields.append(name)
            entity_columns.append((entity.id, evidence_fields.index(name)))
        query = f"SELECT DISTINCT {' '.join(fields)} WHERE {{\n  {body}\n}}"
        evidence_query = f"SELECT {' '.join(evidence_fields)} WHERE {{\n  {body}\n}}"
    return Compiled(
        query, evidence_query, plan_digest(plan),
        tuple(x.id for x in plan.selectors + plan.edges + plan.filters + plan.projections),
        0 if plan.kind == "ask" else public_count,
        tuple(entity_columns),
    )


@dataclass(frozen=True)
class AtomWitness: atom_id: str; status: str; witness: tuple[str, str, str] | None
@dataclass(frozen=True)
class RowWitness: row_key: str; atoms: tuple[AtomWitness, ...]
@dataclass(frozen=True)
class Outcome: kind: str; rows: tuple[tuple[Term, ...], ...] = (); value: bool | None = None; supports: tuple[RowWitness, ...] = (); reason: str | None = None; query: str | None = None


def execute(plan: Plan, catalog: Catalog, graph: Graph | Dataset, *, cancelled: bool = False, timeout_seconds: float | None = None, byte_limit: int | None = None, interrupted_sentinel: bool = False) -> Outcome:
    if cancelled: return Outcome("failed", reason="cancelled")
    if interrupted_sentinel: return Outcome("failed", reason="interrupted_sentinel")
    compiled = compile_plan(plan, catalog); started = time.monotonic()
    try: result = graph.query(compiled.query)
    except Exception as exc: return Outcome("failed", reason="malformed_result:" + type(exc).__name__, query=compiled.query)
    if timeout_seconds is not None and time.monotonic() - started > timeout_seconds: return Outcome("failed", reason="timeout", query=compiled.query)
    try:
        if plan.kind == "ask":
            value = bool(result)
            if not value:
                return Outcome("boolean", value=False, query=compiled.query)
            evidence = tuple(graph.query(compiled.evidence_query))
            if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
                return Outcome("failed", reason="timeout", query=compiled.query)
            if not evidence:
                raise PlanError("true ASK lacks a witness solution")
            bindings = _entity_bindings(compiled, evidence[0])
            support = _supports(plan, catalog, graph, (), bindings)
            return Outcome("boolean", value=True, supports=(support,), query=compiled.query)
        raw_rows = tuple(tuple(row) for row in result)
        rows = tuple(tuple(_from_rdf(v) for v in row) for row in raw_rows)
        if byte_limit is not None and len(json.dumps([tuple(asdict(v) for v in row) for row in rows])) > byte_limit: return Outcome("failed", reason="byte_limit", query=compiled.query)
        if not rows: return Outcome("no_match", rows=(), query=compiled.query)
        evidence_rows = tuple(tuple(row) for row in graph.query(compiled.evidence_query))
        if timeout_seconds is not None and time.monotonic() - started > timeout_seconds: return Outcome("failed", reason="timeout", query=compiled.query)
        supports = tuple(
            _supports(plan, catalog, graph, row, _entity_bindings(compiled, next(
                evidence for evidence in evidence_rows
                if evidence[:compiled.public_count] == raw
            )))
            for row, raw in zip(rows, raw_rows)
        )
        return Outcome("selected", rows=rows, supports=supports, query=compiled.query)
    except Exception as exc: return Outcome("failed", reason="malformed_result:" + type(exc).__name__, query=compiled.query)


def _from_rdf(value: Any) -> Term:
    if isinstance(value, URIRef): return Term("iri", str(value))
    if isinstance(value, Literal): return Term("literal", str(value), str(value.datatype) if value.datatype else None, value.language.lower() if value.language else None)
    raise PlanError("unsupported result term")


def _entity_bindings(compiled: Compiled, row: Any) -> dict[str, Term]:
    bindings = {entity_id: _from_rdf(row[index]) for entity_id, index in compiled.entity_columns}
    if any(term.kind != "iri" for term in bindings.values()):
        raise PlanError("entity result must be an IRI")
    return bindings


def _supports(plan: Plan, catalog: Catalog, graph: Graph | Dataset, row: tuple[Term, ...], bindings: dict[str, Term]) -> RowWitness:
    # Each compiler atom receives one deterministic witness/derivation; no inferred negatives.
    props = {x.key: x for x in catalog.properties}; sels = {x.key: x for x in catalog.selectors}; lens = {x.id: x for x in plan.lenses}
    def triple(source: Term, q: PropertyDef, target: Term) -> tuple[str, str, str]:
        a, b = (target.rdf(), source.rdf()) if q.inverse else (source.rdf(), target.rdf())
        for s, p, o in graph.triples((a, URIRef(q.predicate_iri), b)): return str(s), str(p), str(o)
        raise PlanError("row lacks required witness")
    atoms: list[AtomWitness] = []
    for s in plan.selectors:
        q, term = sels[s.key], bindings.get(s.entity)
        if term is None: raise PlanError("unbound selector witness")
        if q.kind == "target_nodes":
            if term.value not in q.target_iris: raise PlanError("row lacks target-node derivation")
            atoms.append(AtomWitness(s.id, "derived", None))
        else: atoms.append(AtomWitness(s.id, "witnessed", triple(term, PropertyDef("", "", "", str(RDF.type), False, (), False), Term("iri", q.class_iri))))
    for e in plan.edges:
        source = bindings.get(lens[e.source_lens].entity); target = bindings.get(e.target_entity)
        atoms.append(AtomWitness(e.id, "witnessed", triple(source, props[e.property_key], target)))
    for f in plan.filters:
        source = bindings.get(lens[f.lens].entity)
        if source is None: continue
        q = props[f.property_key]
        values = (
            (s for s, _, _ in graph.triples((None, URIRef(q.predicate_iri), source.rdf())))
            if q.inverse else
            (o for _, _, o in graph.triples((source.rdf(), URIRef(q.predicate_iri), None)))
        )
        candidate = f.value if isinstance(f, Eq) else next((Term("iri", str(value)) if isinstance(value, URIRef) else _from_rdf(value) for value in values), None)
        if candidate is not None: atoms.append(AtomWitness(f.id, "derived", triple(source, q, candidate)))
    for p, value in zip(plan.projections, row):
        if isinstance(p, NodeProjection): atoms.append(AtomWitness(p.id, "derived", None))
        else: atoms.append(AtomWitness(p.id, "witnessed", triple(bindings[lens[p.lens].entity], props[p.property_key], value)))
    expected = {x.id for x in plan.selectors + plan.edges + plan.filters + plan.projections}
    if {x.atom_id for x in atoms} != expected or len(atoms) != len(expected): raise PlanError("incomplete atom witness map")
    return RowWitness(_digest({"row": [asdict(x) for x in row], "bindings": {key: asdict(value) for key, value in sorted(bindings.items())}}), tuple(atoms))


if __name__ == "__main__":
    EX = "https://example.test/"
    shapes = Graph().parse(data=f"@prefix sh: <http://www.w3.org/ns/shacl#>. @prefix ex: <{EX}>. ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [sh:path ex:p; sh:maxCount 1].", format="turtle")
    data = Graph().parse(data=f"@prefix ex: <{EX}>. ex:a a ex:E; ex:p \"ok\".", format="turtle")
    c = Catalog.build([shapes]); selector, prop = c.selectors[0], c.properties[0]
    raw = {"kind":"select","catalog_revision":c.revision,"entities":[{"id":"person","binding":None}],"selectors":[{"id":"root","entity":"person","key":selector.key}],"lenses":[{"id":"view","entity":"person","key":c.lenses[0].key}],"edges":[],"filters":[],"projections":[{"kind":"node","id":"who","entity":"person"},{"kind":"field","id":"name","lens":"view","property_key":prop.key,"branch_key":prop.branch_keys[0],"required":True}]}
    answer = execute(normalize(raw, c), c, data)
    assert answer.kind == "selected" and len(answer.rows) == 1 and len(answer.supports[0].atoms) == 3
    assert Catalog.reload(json.loads(json.dumps(c.dump()))) == c
    print("phase0 kernel self-check passed")
