from __future__ import annotations

import copy
import json
import time
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from rdflib import Dataset, Graph, Literal, URIRef

from shapelens import (
    ApplicationOverlay,
    AuthorizationScope,
    BooleanResult,
    Catalog,
    CatalogError,
    CatalogPolicy,
    DatasetScope,
    EvidenceError,
    ExecutionRequest,
    Failed,
    NoMatch,
    PlanError,
    PolicyError,
    PolicyLimited,
    QualificationRecord,
    QueryPolicy,
    Selected,
    SemanticQualification,
    ShapeQueryEngine,
    ShapeSource,
    Term,
    Unsupported,
    normalize_plan,
    render_result,
    validate_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
SHAPE_PATHS = (
    "phase0/corpus/shapes/staffing-skills.ttl",
    "phase0/corpus/shapes/service-operations.ttl",
    "phase0/corpus/shapes/research-publication-catalog.ttl",
    "phase0/fixtures/artifacts/semantic-shapes.ttl",
)
SCALAR_OVERRIDES = (
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/title"),
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/publicationYear"),
    ("https://catalog.example.org/ns/ResearcherShape", "https://catalog.example.org/ns/displayName"),
)


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def reviewed_source(relative: str, *, trust: str = "trusted", closure_trust=()) -> ShapeSource:
    graph = Graph().parse(ROOT / relative)
    qualification = SemanticQualification.reviewed_graph(
        graph,
        owner="phase-1 conformance owner",
        fixture_revision="phase0:c35149a9",
        fixture_ids=("accepted-phase0-fixtures",),
    )
    return ShapeSource(graph, relative, "ShapeLens project", trust, qualification, tuple(closure_trust))


def accepted_catalog(*, trust: str = "trusted", build_id: str = "phase1-conformance") -> Catalog:
    sources = tuple(reviewed_source(path, trust=trust) for path in SHAPE_PATHS)
    signatures = {
        (record.shape_term, json.loads(record.value)["predicate"]): record.value
        for source in sources
        for record in source.qualification.records
        if record.behavior == "property"
    }
    qualification = SemanticQualification(
        "research information office",
        "phase0:c35149a9",
        tuple(
            QualificationRecord(
                shape,
                "scalar_projection",
                signatures[(shape, predicate)],
                ("research-overlay",),
            )
            for shape, predicate in SCALAR_OVERRIDES
        ),
    )
    overlay = ApplicationOverlay(
        "phase0-research-projections",
        "executable",
        "research information office",
        True,
        SCALAR_OVERRIDES,
        qualification,
    )
    return Catalog.build(sources, overlays=(overlay,), build_id=build_id)


def remap_plan(raw: dict, old: dict, new: Catalog) -> dict:
    raw = copy.deepcopy(raw)
    old_lenses = {item["key"]: item for item in old["lenses"]}
    new_lenses = {item.shape_term: item for item in new.lenses}
    lens_map = {key: new_lenses[item["shape_term"]].key for key, item in old_lenses.items()}
    new_properties = {(next(x.shape_term for x in new.lenses if x.key == item.lens_key), item.predicate_iri, item.inverse): item for item in new.properties}
    property_map = {}
    branch_map = {}
    for item in old["properties"]:
        shape = old_lenses[item["lens_key"]]["shape_term"]
        candidate = new_properties[(shape, item["predicate_iri"], item["inverse"])]
        property_map[item["key"]] = candidate.key
        for index, key in enumerate(item["branch_keys"]):
            branch_map[key] = candidate.branch_keys[index]
    new_selectors = {
        (
            next(x.shape_term for x in new.lenses if x.key == item.lens_key),
            item.kind,
            item.classes,
            item.target_iris,
        ): item
        for item in new.selectors
    }
    selector_map = {}
    for item in old["selectors"]:
        shape = old_lenses[item["lens_key"]]["shape_term"]
        classes = (item["class_iri"],) if item["class_iri"] else ()
        targets = tuple(item["target_iris"])
        selector_map[item["key"]] = new_selectors[(shape, item["kind"], classes, targets)].key
    raw["catalog_revision"] = new.revision
    for item in raw["lenses"]:
        item["key"] = lens_map[item["key"]]
    for item in raw["selectors"]:
        item["key"] = selector_map[item["key"]]
    for group in ("edges", "filters", "projections"):
        for item in raw[group]:
            if "property_key" in item:
                item["property_key"] = property_map[item["property_key"]]
            if "branch_key" in item:
                item["branch_key"] = branch_map[item["branch_key"]]
    properties = {item.key: item for item in new.properties}
    entity_bindings = {item["id"]: item.get("binding") for item in raw["entities"]}
    for item in raw["filters"]:
        if item.get("kind") == "eq":
            prop = properties[item["property_key"]]
            item["branch_key"] = next(
                (branch.key for branch in prop.branches if branch.accepts(Term.load(item["value"]))),
                prop.branches[0].key,
            )
    for item in raw["edges"]:
        prop = properties[item["property_key"]]
        binding = entity_bindings[item["target_entity"]]
        item["branch_key"] = next(
            branch.key for branch in prop.branches
            if branch.accepts(Term.load(binding)) if binding is not None
        ) if binding is not None else next(branch.key for branch in prop.branches if branch.accepts_iri)
    return raw


def data_graph(mode: str, paths: list[str]) -> Graph | Dataset:
    graph = Graph() if mode == "graph" else Dataset()
    for path in paths:
        graph.parse(ROOT / path)
    return graph


def term_key(value) -> tuple:
    if isinstance(value, Term):
        return value.kind, value.value, value.datatype, value.language
    if isinstance(value, URIRef):
        return "iri", str(value), None, None
    if isinstance(value, Literal):
        return "literal", str(value), str(value.datatype) if value.datatype else None, value.language.lower() if value.language else None
    raise AssertionError(type(value))


def simple_engine(*, shape_text: str, data_text: str, authorization=None, policy=None, trust="trusted", qualification=None, closure_trust=(), build_id="simple"):
    shapes = Graph().parse(data=shape_text, format="turtle")
    data = Graph().parse(data=data_text, format="turtle")
    qualification = qualification or SemanticQualification.reviewed_graph(
        shapes, owner="test", fixture_revision="r1", fixture_ids=("case",)
    )
    source = ShapeSource(shapes, "test-shapes", "test", trust, qualification, tuple(closure_trust))
    catalog = Catalog.build((source,), build_id=build_id)
    return ShapeQueryEngine(
        data=data,
        catalog=catalog,
        authorization=authorization or AuthorizationScope.allow_all(),
        dataset_scope=DatasetScope("test-data"),
        policy=policy,
    )


def single_plan(engine: ShapeQueryEngine, *, field=True, required=True, ask=False):
    prop = engine.catalog.properties[0]
    projections = [] if ask else [{"id": "node", "kind": "node", "entity": "node"}]
    if field and not ask:
        projections.append({"id": "field", "kind": "field", "lens": "view", "property_key": prop.key, "branch_key": prop.branch_keys[0], "required": required})
    return {
        "kind": "ask" if ask else "select",
        "catalog_revision": engine.catalog.revision,
        "entities": [{"id": "node", "binding": None}],
        "selectors": [{"id": "population", "entity": "node", "key": engine.catalog.selectors[0].key}],
        "lenses": [{"id": "view", "entity": "node", "key": engine.catalog.lenses[0].key}],
        "edges": [],
        "filters": [{"id": "exists", "kind": "exists", "lens": "view", "property_key": prop.key}],
        "projections": projections,
    }


class Phase1Conformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = accepted_catalog()
        cls.old_catalog = load_json("phase0/fixtures/catalog.json")
        cls.manifest = load_json("phase0/fixtures/manifest.json")

    def test_sl_001_to_010_accepted_kernel_matrix(self):
        """SL-001..010: all 35 frozen plans match or fail closed in both local modes."""
        cells = 0
        rejected = 0
        for record in self.manifest["records"]:
            raw = remap_plan(load_json(record["plan_path"]), self.old_catalog, self.catalog)
            for mode in self.manifest["adapter_modes"]:
                graph = data_graph(mode, record["data_paths"])
                engine = ShapeQueryEngine(data=graph, catalog=self.catalog, authorization=AuthorizationScope.allow_all(), dataset_scope=DatasetScope(f"{record['fixture_id']}:{mode}"))
                outcome = engine.execute_plan(raw)
                oracle = graph.query((ROOT / record["semantic_oracle_query_path"]).read_text())
                if record["oracle_variables"]:
                    expected = Counter(tuple(term_key(row[name]) for name in record["oracle_variables"]) for row in oracle)
                    actual = Counter(tuple(term_key(value) for value in row.values) for row in outcome.rows) if isinstance(outcome, Selected) else Counter()
                    self.assertEqual(expected, actual, (record["fixture_id"], mode, outcome))
                    if record["fixture_id"] == "semantic-identity-datatype-miss":
                        self.assertFalse(expected)
                        self.assertIsInstance(outcome, Unsupported)
                        rejected += 1
                    else:
                        self.assertIsInstance(outcome, Selected if expected else NoMatch)
                    if isinstance(outcome, Selected):
                        for certificate in outcome.packet.certificates:
                            self.assertEqual(set(certificate.plan_atom_support[i].atom_id for i in range(len(certificate.plan_atom_support))), set(engine.explain_plan(raw).atom_ids))
                else:
                    expected = bool(oracle)
                    self.assertIsInstance(outcome, BooleanResult if expected else NoMatch, (record["fixture_id"], mode, outcome))
                cells += 1
        self.assertEqual(cells, 70)
        self.assertEqual(rejected, 2)

    def test_sl_001_to_010_validation_boundaries(self):
        for raw in (
            {"kind": "iri", "value": "https://e/bad\niri"},
            {"kind": "iri", "value": "relative"},
            {"kind": "literal", "value": "x", "datatype": "https://e/t", "language": "en"},
        ):
            with self.assertRaises(PlanError):
                Term.load(raw)
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p; sh:maxCount 1 ]."""
        engine = simple_engine(
            shape_text=shapes,
            data_text="@prefix ex:<https://e/>. ex:a a ex:E; ex:p ex:value.",
        )
        raw = single_plan(engine)
        extra = copy.deepcopy(raw)
        extra["query"] = "SERVICE <https://attacker/> {}"
        self.assertIsInstance(engine.execute_plan(extra), Unsupported)
        non_string = copy.deepcopy(raw)
        non_string[1] = "not a field name"
        self.assertIsInstance(engine.execute_plan(non_string), Unsupported)
        self.assertIsInstance(engine.execute_plan(raw, request={"extent": "complete"}), Unsupported)
        plan = engine.validate_plan(raw)
        self.assertIsInstance(engine.execute_plan(replace(plan, kind="update")), Unsupported)
        field = next(item for item in plan.projections if hasattr(item, "required"))
        invalid_field = replace(
            plan,
            projections=tuple(replace(item, required="yes") if item == field else item for item in plan.projections),
        )
        self.assertIsInstance(engine.execute_plan(invalid_field), Unsupported)
        with self.assertRaises(PolicyError):
            engine.compile(plan, limit=-1)
        duplicate = copy.deepcopy(raw)
        duplicate["selectors"].append({**duplicate["selectors"][0], "id": "other"})
        self.assertIsInstance(engine.execute_plan(duplicate), Unsupported)
        duplicate_lens = copy.deepcopy(raw)
        duplicate_lens["lenses"].append({**duplicate_lens["lenses"][0], "id": "other-view"})
        self.assertIsInstance(engine.execute_plan(duplicate_lens), Unsupported)
        unused_lens = copy.deepcopy(raw)
        unused_lens["filters"] = []
        unused_lens["projections"] = [unused_lens["projections"][0]]
        self.assertIsInstance(engine.execute_plan(unused_lens), Unsupported)
        unknown = copy.deepcopy(raw)
        unknown["filters"][0]["lens"] = "missing"
        self.assertIsInstance(engine.execute_plan(unknown), Unsupported)
        disconnected = copy.deepcopy(raw)
        disconnected["entities"].append({
            "id": "helper", "binding": {"kind": "iri", "value": "https://e/helper"}
        })
        self.assertIsInstance(engine.execute_plan(disconnected), Unsupported)
        disconnected_ask = single_plan(engine, field=False, ask=True)
        disconnected_ask["entities"].append({
            "id": "helper", "binding": {"kind": "iri", "value": "https://e/helper"}
        })
        self.assertIsInstance(engine.execute_plan(disconnected_ask), Unsupported)

        class_engine = simple_engine(
            shape_text="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E;
                sh:property [ sh:path ex:p; sh:class ex:Allowed; sh:maxCount 1 ].""",
            data_text="@prefix ex:<https://e/>. ex:a a ex:E; ex:p ex:wrong.",
        )
        self.assertIsInstance(class_engine.execute_plan(single_plan(class_engine)), NoMatch)

        in_engine = simple_engine(
            shape_text="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E;
                sh:property [ sh:path ex:p; sh:in (ex:allowed) ].""",
            data_text="@prefix ex:<https://e/>. ex:a a ex:E; ex:p ex:other.",
        )
        prop = in_engine.catalog.properties[0]
        outside = single_plan(in_engine, field=False, ask=True)
        outside["filters"] = [{
            "id": "eq", "kind": "eq", "lens": "view",
            "property_key": prop.key, "branch_key": prop.branch_keys[0],
            "value": {"kind": "iri", "value": "https://e/other"},
        }]
        self.assertIsInstance(in_engine.execute_plan(outside), Unsupported)
        datatype_engine = simple_engine(
            shape_text="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix xsd:<http://www.w3.org/2001/XMLSchema#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E;
                sh:property [ sh:path ex:p; sh:datatype xsd:integer ].""",
            data_text='@prefix ex:<https://e/>. ex:a a ex:E; ex:p "wrong".',
        )
        prop = datatype_engine.catalog.properties[0]
        wrong_type = single_plan(datatype_engine, field=False, ask=True)
        wrong_type["filters"] = [{
            "id": "eq", "kind": "eq", "lens": "view",
            "property_key": prop.key, "branch_key": prop.branch_keys[0],
            "value": {"kind": "literal", "value": "wrong"},
        }]
        self.assertIsInstance(datatype_engine.execute_plan(wrong_type), Unsupported)

    def test_sl_011_catalog_trust_qualification_and_authorization(self):
        """SL-011: trust, exact qualification, closure trust, and authorization are independent gates."""
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
            ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:public ], [ sh:path ex:protected ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:E; ex:public ex:x; ex:protected ex:y."
        graph = Graph().parse(data=shapes, format="turtle")
        reviewed = SemanticQualification.reviewed_graph(
            graph, owner="owner", fixture_revision="r", fixture_ids=("f",)
        )
        qualification = SemanticQualification(
            "owner",
            "r",
            tuple(
                record
                for record in reviewed.records
                if record.behavior == "selector" or "https://e/public" in record.value
            ),
        )
        untrusted = simple_engine(shape_text=shapes, data_text=data, trust="untrusted", qualification=qualification, build_id="u")
        self.assertIsInstance(untrusted.execute_plan(single_plan(untrusted, field=False)), Unsupported)
        closure = simple_engine(shape_text=shapes, data_text=data, closure_trust=("untrusted",), qualification=qualification, build_id="c")
        self.assertIsInstance(closure.execute_plan(single_plan(closure, field=False)), Unsupported)
        trusted = simple_engine(shape_text=shapes, data_text=data, qualification=qualification, build_id="t")
        protected = next(x for x in trusted.catalog.properties if x.predicate_iri.endswith("protected"))
        raw = single_plan(trusted, field=False)
        raw["filters"] = [{"id":"exists","kind":"exists","lens":"view","property_key":protected.key}]
        self.assertIsInstance(trusted.execute_plan(raw), Unsupported)
        public = next(x for x in trusted.catalog.properties if x.predicate_iri.endswith("public"))
        denied_engine = ShapeQueryEngine(data=trusted.data, catalog=trusted.catalog, authorization=AuthorizationScope("deny", allowed_properties=frozenset()), dataset_scope=trusted.dataset_scope)
        raw["filters"][0]["property_key"] = public.key
        self.assertIsInstance(denied_engine.execute_plan(raw), PolicyLimited)
        self.assertNotEqual(untrusted.catalog.revision, trusted.catalog.revision)

        directional = Graph().parse(
            data="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E;
                sh:property [ sh:path ex:p ], [ sh:path [ sh:inversePath ex:p ] ].""",
            format="turtle",
        )
        all_records = SemanticQualification.reviewed_graph(
            directional, owner="owner", fixture_revision="r", fixture_ids=("direction",)
        )
        direct_only = SemanticQualification(
            "owner", "r",
            tuple(record for record in all_records.records if record.behavior == "selector" or '"inverse":false' in record.value),
        )
        catalog = Catalog.build(
            (ShapeSource(directional, "directional", "owner", "trusted", direct_only),),
            build_id="directional",
        )
        self.assertTrue(next(prop for prop in catalog.properties if not prop.inverse).qualified)
        self.assertFalse(next(prop for prop in catalog.properties if prop.inverse).qualified)
        direct_signature = next(
            record.value
            for record in all_records.records
            if record.behavior == "property" and '"inverse":false' in record.value
        )
        overlay = ApplicationOverlay(
            "exact", "executable", "owner", True,
            (("https://e/S", "https://e/p"),),
            SemanticQualification(
                "owner", "r",
                (QualificationRecord("https://e/S", "scalar_projection", direct_signature, ("direction",)),),
            ),
        )
        overlaid = Catalog.build(
            (ShapeSource(directional, "directional", "owner", "trusted", all_records),),
            overlays=(overlay,),
            build_id="exact-overlay",
        )
        self.assertTrue(next(prop for prop in overlaid.properties if not prop.inverse).scalar)
        self.assertFalse(next(prop for prop in overlaid.properties if prop.inverse).scalar)

    def test_sl_012_population_and_context_are_separate(self):
        """SL-012: a joined value does not import the target lens selector."""
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:A a sh:NodeShape; sh:targetClass ex:AClass; sh:property [ sh:path ex:rel; sh:class ex:BClass ].
          ex:B a sh:NodeShape; sh:targetClass ex:BClass; sh:targetNode ex:notTheJoinedNode; sh:property [ sh:path ex:name; sh:maxCount 1 ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:AClass; ex:rel ex:b. ex:b a ex:BClass; ex:name \"B\"."
        engine = simple_engine(shape_text=shapes, data_text=data)
        a_lens = next(x for x in engine.catalog.lenses if x.shape_term == "https://e/A")
        b_lens = next(x for x in engine.catalog.lenses if x.shape_term == "https://e/B")
        a_selector = next(x for x in engine.catalog.selectors if x.lens_key == a_lens.key)
        rel = next(x for x in engine.catalog.properties if x.lens_key == a_lens.key)
        name = next(x for x in engine.catalog.properties if x.lens_key == b_lens.key)
        raw = {"kind":"select","catalog_revision":engine.catalog.revision,"entities":[{"id":"a","binding":None},{"id":"b","binding":None}],"selectors":[{"id":"root","entity":"a","key":a_selector.key}],"lenses":[{"id":"av","entity":"a","key":a_lens.key},{"id":"bv","entity":"b","key":b_lens.key}],"edges":[{"id":"edge","source_lens":"av","property_key":rel.key,"branch_key":rel.branch_keys[0],"target_entity":"b"}],"filters":[],"projections":[{"id":"name","kind":"field","lens":"bv","property_key":name.key,"branch_key":name.branch_keys[0],"required":True}]}
        outcome = engine.execute_plan(raw)
        self.assertIsInstance(outcome, Selected)
        self.assertEqual(outcome.rows[0].values[0].value, "B")
        self.assertNotIn("notTheJoinedNode", engine.explain_plan(raw).query)
        constrained = copy.deepcopy(raw)
        constrained["selectors"].append({"id": "joined-selector", "entity": "b", "key": next(x for x in engine.catalog.selectors if x.lens_key == b_lens.key).key})
        self.assertIsInstance(engine.execute_plan(constrained), Selected)

    def test_sl_013_targetless_and_invalid_targets_fail_closed(self):
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass \"not-a-class\"; sh:targetNode \"not-an-iri\";
            sh:property [ sh:path ex:p ], [ sh:path (ex:p ex:q) ]."""
        data = "@prefix ex:<https://e/>. ex:a ex:p ex:b."
        engine = simple_engine(shape_text=shapes, data_text=data)
        self.assertFalse(engine.catalog.selectors)
        self.assertEqual(
            {item.code for item in engine.catalog.diagnostics},
            {"target_class_non_iri", "target_node_non_iri", "path_unsupported"},
        )
        prop = engine.catalog.properties[0]
        raw = {"kind":"ask","catalog_revision":engine.catalog.revision,"entities":[{"id":"x","binding":None}],"selectors":[],"lenses":[{"id":"l","entity":"x","key":engine.catalog.lenses[0].key}],"edges":[],"filters":[{"id":"f","kind":"exists","lens":"l","property_key":prop.key}],"projections":[]}
        self.assertIsInstance(engine.execute_plan(raw), Unsupported)
        cyclic = Graph().parse(
            data="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:property [ sh:path ex:p; sh:in _:list ].
              _:list rdf:first ex:a; rdf:rest _:list.""",
            format="turtle",
        )
        with self.assertRaises(CatalogError):
            Catalog.build(
                (ShapeSource(cyclic, "cyclic", "owner", "trusted", SemanticQualification("owner", "r", ())),),
                build_id="cyclic",
            )

    def test_sl_014_canonicalization_and_catalog_identity(self):
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p; sh:maxCount 1 ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:E; ex:p \"x\"."
        one = simple_engine(shape_text=shapes, data_text=data, build_id="one")
        dumped = json.loads(json.dumps(one.catalog.dump()))
        self.assertEqual(Catalog.reload(dumped), one.catalog)
        tampered = copy.deepcopy(dumped)
        tampered["lenses"][0]["trusted"] = False
        with self.assertRaises(CatalogError):
            Catalog.reload(tampered)
        with self.assertRaises(CatalogError):
            Catalog.reload([])
        self.assertTrue(one.catalog.lenses[0].portable_key)
        self.assertIsNone(one.catalog.properties[0].portable_key)
        two = simple_engine(shape_text=shapes, data_text=data, build_id="two")
        self.assertNotEqual(one.catalog.revision, two.catalog.revision)
        raw = single_plan(one)
        alt = copy.deepcopy(raw)
        alt["entities"][0]["id"] = "renamed"
        for item in alt["selectors"]:
            item["entity"] = "renamed"
        for item in alt["lenses"]:
            item["entity"] = "renamed"
            item["id"] = "renamed-view"
        alt["filters"][0]["lens"] = "renamed-view"
        for item in alt["projections"]:
            if item["kind"] == "node": item["entity"] = "renamed"
            else: item["lens"] = "renamed-view"
        self.assertEqual(one.explain_plan(raw).plan_digest, one.explain_plan(alt).plan_digest)
        stale = copy.deepcopy(raw); stale["catalog_revision"] = two.catalog.revision
        self.assertIsInstance(two.execute_plan(stale), Unsupported)

    def test_sl_015_scalar_and_optional_projection_rules(self):
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:many ], [ sh:path ex:one; sh:maxCount 1 ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:E; ex:many 1,2."
        engine = simple_engine(shape_text=shapes, data_text=data)
        many = next(x for x in engine.catalog.properties if x.predicate_iri.endswith("many"))
        raw = single_plan(engine)
        raw["projections"][0] = {"id":"many","kind":"field","lens":"view","property_key":many.key,"branch_key":many.branch_keys[0],"required":True}
        raw["projections"] = raw["projections"][:1]
        self.assertIsInstance(engine.execute_plan(raw), Unsupported)
        one = next(x for x in engine.catalog.properties if x.predicate_iri.endswith("one"))
        raw["filters"] = []
        raw["projections"] = [{"id":"one","kind":"field","lens":"view","property_key":one.key,"branch_key":one.branch_keys[0],"required":False}]
        outcome = engine.execute_plan(raw)
        self.assertIsInstance(outcome, Selected)
        self.assertIsNone(outcome.rows[0].values[0])
        self.assertEqual(outcome.packet.certificates[0].plan_atom_support[-1].status, "optional_unbound")
        violated = simple_engine(
            shape_text="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:one; sh:maxCount 1 ].""",
            data_text="@prefix ex:<https://e/>. ex:a a ex:E; ex:one 1,2.",
        )
        self.assertIsInstance(violated.execute_plan(single_plan(violated, required=True)), Failed)

    def test_sl_016_evidence_mutations_are_rejected(self):
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p; sh:maxCount 1 ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:E; ex:p \"x\"."
        engine = simple_engine(shape_text=shapes, data_text=data)
        raw = single_plan(engine)
        plan = engine.validate_plan(raw)
        outcome = engine.execute_plan(raw)
        self.assertIsInstance(outcome, Selected)
        compiled = engine.compile(plan, limit=engine.policy.max_result_rows + 1)
        validate_evidence(plan, compiled, outcome.packet, outcome.rows, catalog=engine.catalog, data=engine.data)
        certificate = outcome.packet.certificates[0]
        broken = replace(certificate, plan_atom_support=certificate.plan_atom_support[:-1])
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, certificates=(broken,)), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, execution_complete=False), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, result_extent_satisfied=False), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, certificates=(certificate, certificate)), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, replace(compiled, digest="sha256:wrong"), outcome.packet, outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, replace(compiled, text="ASK WHERE {}"), outcome.packet, outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, outcome.packet, (replace(outcome.rows[0], values=(*outcome.rows[0].values, Term("literal", "extra"))),), catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, execution_id="wrong"), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, plan_digest="sha256:wrong"), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, dataset_scope=DatasetScope("other")), outcome.rows, catalog=engine.catalog, data=engine.data)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, certificates=(replace(certificate, entity_bindings=()),)), outcome.rows, catalog=engine.catalog, data=engine.data)
        triple = next(item for item in outcome.packet.evidence if hasattr(item, "subject"))
        invented = replace(triple, subject=Term("iri", "https://e/invented"))
        evidence = tuple(invented if item.id == triple.id else item for item in outcome.packet.evidence)
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, evidence=evidence), outcome.rows, catalog=engine.catalog, data=engine.data)
        illegal = replace(certificate.plan_atom_support[0], status="unknown")
        mutated = replace(certificate, plan_atom_support=(illegal, *certificate.plan_atom_support[1:]))
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, certificates=(mutated,)), outcome.rows, catalog=engine.catalog, data=engine.data)
        invalid_derivation = replace(
            certificate.plan_atom_support[0],
            derived_from_entity_ids=("wrong",),
        )
        mutated = replace(certificate, plan_atom_support=(invalid_derivation, *certificate.plan_atom_support[1:]))
        with self.assertRaises(EvidenceError):
            validate_evidence(plan, compiled, replace(outcome.packet, certificates=(mutated,)), outcome.rows, catalog=engine.catalog, data=engine.data)

    def test_sl_017_outcomes_failure_honesty_and_rendering(self):
        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p ]."""
        engine = simple_engine(shape_text=shapes, data_text="@prefix ex:<https://e/>. ex:a a ex:E; ex:p ex:b.")
        ask_raw = single_plan(engine, field=False, ask=True)
        true = engine.execute_plan(ask_raw)
        self.assertIsInstance(true, BooleanResult)
        self.assertFalse(true.packet.certificates)
        ask_plan = engine.validate_plan(ask_raw)
        ask_compiled = engine.compile(ask_plan)
        contradictory_query = engine._query_evidence(
            ask_compiled,
            true.packet.execution_id,
            completed=True,
            result_kind="ask",
            boolean_value=True,
            more_results=True,
        )
        evidence = tuple(
            contradictory_query if hasattr(item, "boolean_value") else item
            for item in true.packet.evidence
        )
        with self.assertRaises(EvidenceError):
            validate_evidence(
                ask_plan,
                ask_compiled,
                replace(true.packet, evidence=evidence, result_set_completeness="incomplete"),
                (),
                catalog=engine.catalog,
                data=engine.data,
            )
        empty = simple_engine(shape_text=shapes, data_text="@prefix ex:<https://e/>.")
        false = empty.execute_plan(single_plan(empty, field=False, ask=True))
        self.assertIsInstance(false, NoMatch)
        self.assertIn("authorization scope", render_result(false))
        self.assertFalse(false.packet.certificates)
        cancelled = engine.execute_plan(single_plan(engine, field=False, ask=True), request=ExecutionRequest("complete", cancelled=True))
        self.assertIsInstance(cancelled, Failed)

        class BrokenGraph:
            def query(self, query):
                raise RuntimeError("broken")
        broken = ShapeQueryEngine(data=BrokenGraph(), catalog=engine.catalog, authorization=engine.authorization, dataset_scope=engine.dataset_scope)
        self.assertIsInstance(broken.execute_plan(single_plan(broken, field=False, ask=True)), Failed)
        class MalformedGraph:
            def query(self, query):
                return []
        malformed = ShapeQueryEngine(data=MalformedGraph(), catalog=engine.catalog, authorization=engine.authorization, dataset_scope=engine.dataset_scope)
        self.assertIsInstance(malformed.execute_plan(single_plan(malformed, field=False, ask=True)), Failed)
        limited = ShapeQueryEngine(data=engine.data, catalog=engine.catalog, authorization=engine.authorization, dataset_scope=engine.dataset_scope, policy=QueryPolicy(max_result_rows=1))
        self.assertIsInstance(limited.execute_plan(single_plan(limited, field=False), request=ExecutionRequest.examples(2)), PolicyLimited)

    def test_sl_018_named_graph_scope_is_enforced_end_to_end(self):
        shapes = Graph().parse(
            data="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p; sh:maxCount 1 ].""",
            format="turtle",
        )
        qualification = SemanticQualification.reviewed_graph(
            shapes, owner="test", fixture_revision="r1", fixture_ids=("named-graph",)
        )
        catalog = Catalog.build((ShapeSource(shapes, "s", "o", "trusted", qualification),), build_id="graphs")
        dataset = Dataset()
        dataset.graph(URIRef("https://e/allowed")).parse(data="@prefix ex:<https://e/>. ex:a a ex:E; ex:p \"allowed\".", format="turtle")
        dataset.graph(URIRef("https://e/denied")).parse(data="@prefix ex:<https://e/>. ex:b a ex:E; ex:p \"denied\".", format="turtle")
        engine = ShapeQueryEngine(
            data=dataset,
            catalog=catalog,
            authorization=AuthorizationScope("scoped", allowed_graphs=frozenset({"https://e/allowed"})),
            dataset_scope=DatasetScope("named", graph_iris=("https://e/allowed",)),
        )
        outcome = engine.execute_plan(single_plan(engine))
        self.assertIsInstance(outcome, Selected)
        self.assertEqual({value.value for row in outcome.rows for value in row.values if value}, {"allowed", "https://e/a"})
        self.assertIn("FROM <https://e/allowed>", engine.explain_plan(single_plan(engine)).query)
        denied = ShapeQueryEngine(
            data=dataset,
            catalog=catalog,
            authorization=AuthorizationScope("none", allowed_graphs=frozenset()),
            dataset_scope=DatasetScope("named", graph_iris=("https://e/allowed",)),
        )
        self.assertIsInstance(denied.execute_plan(single_plan(denied)), PolicyLimited)

    def test_sl_018_policy_limits_fail_closed(self):
        for kwargs in (
            {"max_entities": 1.5},
            {"deadline_seconds": float("inf")},
            {"deadline_seconds": float("nan")},
            {"max_retries": 1},
        ):
            with self.assertRaises(PolicyError):
                QueryPolicy(**kwargs)
        with self.assertRaises(CatalogError):
            CatalogPolicy(max_source_bytes=0)

        shapes = """@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
          ex:S a sh:NodeShape; sh:targetClass ex:E; sh:property [ sh:path ex:p; sh:maxCount 1 ]."""
        data = "@prefix ex:<https://e/>. ex:a a ex:E; ex:p \"a value large enough to exceed one byte\"."
        limited = simple_engine(shape_text=shapes, data_text=data, policy=QueryPolicy(max_entities=1))
        too_many = single_plan(limited)
        too_many["entities"].append({"id": "extra", "binding": {"kind": "iri", "value": "https://e/x"}})
        self.assertIsInstance(limited.execute_plan(too_many), PolicyLimited)
        bytes_limited = simple_engine(shape_text=shapes, data_text=data, policy=QueryPolicy(max_result_bytes=1))
        self.assertIsInstance(bytes_limited.execute_plan(single_plan(bytes_limited)), Failed)
        ast_limited = simple_engine(shape_text=shapes, data_text=data, policy=QueryPolicy(max_ast_nodes=1))
        self.assertIsInstance(ast_limited.execute_plan(single_plan(ast_limited)), PolicyLimited)

        base = simple_engine(shape_text=shapes, data_text=data)
        class SlowGraph:
            def query(self, query):
                time.sleep(0.01)
                return base.data.query(query)
        slow = ShapeQueryEngine(
            data=SlowGraph(), catalog=base.catalog, authorization=base.authorization,
            dataset_scope=base.dataset_scope, policy=QueryPolicy(deadline_seconds=0.001),
        )
        self.assertIsInstance(slow.execute_plan(single_plan(slow, field=False, ask=True)), Failed)

        source = reviewed_source("phase0/fixtures/artifacts/semantic-shapes.ttl")
        with self.assertRaises(CatalogError):
            Catalog.build((source,), build_id="triple-limit", policy=CatalogPolicy(max_source_triples=1))
        with self.assertRaises(CatalogError):
            Catalog.build((source,), build_id="byte-limit", policy=CatalogPolicy(max_source_bytes=1))
        with self.assertRaises(CatalogError):
            Catalog.build((source,), build_id="lens-limit", policy=CatalogPolicy(max_lens_card_bytes=1))

        recursive = Graph().parse(
            data="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:property [ sh:path ex:p; sh:node ex:S ].""",
            format="turtle",
        )
        with self.assertRaises(CatalogError):
            Catalog.build(
                (ShapeSource(recursive, "recursive", "owner", "trusted", SemanticQualification("owner", "r", ())),),
                build_id="recursive",
            )

        inverse = Graph().parse(
            data="""@prefix sh:<http://www.w3.org/ns/shacl#>. @prefix ex:<https://e/>.
              ex:S a sh:NodeShape; sh:property [ sh:path [ sh:inversePath ex:p ] ].""",
            format="turtle",
        )
        qualification = SemanticQualification.reviewed_graph(
            inverse, owner="owner", fixture_revision="r", fixture_ids=("inverse",)
        )
        catalog = Catalog.build(
            (ShapeSource(inverse, "inverse", "owner", "trusted", qualification),),
            build_id="path-limit", policy=CatalogPolicy(max_path_depth=1),
        )
        self.assertFalse(catalog.properties)
        self.assertIn("path_depth_exceeded", {item.code for item in catalog.diagnostics})


if __name__ == "__main__":
    unittest.main()
