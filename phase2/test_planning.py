import copy
import unittest

from rdflib import Graph

from shapelens import (
    AuthorizationScope,
    Catalog,
    DatasetScope,
    SemanticQualification,
    ShapeQueryEngine,
    ShapeSource,
)
from phase2.planning import (
    EntityLabel,
    IntentCoverage,
    IntentItem,
    PlannerCard,
    PlannerReply,
    ShapeRAG,
    cards_from_catalog,
    resolve_entity,
    validate_coverage,
)

class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shapes = Graph().parse(
            data="""
                @prefix ex: <https://example.test/> .
                @prefix sh: <http://www.w3.org/ns/shacl#> .
                ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
                  sh:property [ sh:path ex:workedOn ; sh:class ex:Project ] .
            """,
            format="turtle",
        )
        qualification = SemanticQualification.reviewed_graph(
            shapes, owner="test", fixture_revision="r1", fixture_ids=("planning",)
        )
        cls.catalog = Catalog.build(
            (ShapeSource(shapes, "planning-shapes", "test", "trusted", qualification),),
            build_id="planning-test",
        )
        data = Graph().parse(
            data="""
                @prefix ex: <https://example.test/> .
                ex:alice a ex:Person ; ex:workedOn ex:atlas .
                ex:atlas a ex:Project .
            """,
            format="turtle",
        )
        cls.engine = ShapeQueryEngine(
            data=data,
            catalog=cls.catalog,
            authorization=AuthorizationScope.allow_all(),
            dataset_scope=DatasetScope("planning-test"),
        )
        prop = cls.catalog.properties[0]
        cls.plan = {
            "kind": "ask",
            "catalog_revision": cls.catalog.revision,
            "entities": [{"id": "employee", "binding": None}, {"id": "project", "binding": None}],
            "selectors": [],
            "lenses": [{"id": "staffing", "entity": "employee", "key": cls.catalog.lenses[0].key}],
            "edges": [
                {
                    "id": "worked",
                    "source_lens": "staffing",
                    "property_key": prop.key,
                    "branch_key": prop.branch_keys[0],
                    "target_entity": "project",
                }
            ],
            "filters": [],
            "projections": [],
        }

    def test_cards_are_explicitly_provider_approved_and_retrieved(self):
        lens = self.catalog.lenses[0]
        prop = self.catalog.properties[0]
        annotations = {
            lens.key: {
                "provider_allowed": True,
                "label": "employee staffing",
                "aliases": ["staffed"],
                "description": "Employee project assignments.",
            },
            prop.key: {
                "provider_allowed": False,
                "label": "worked on",
                "description": "Project relationship.",
            },
        }
        cards = cards_from_catalog(self.catalog, annotations)
        self.assertEqual([lens.key], [card.key for card in cards])
        self.assertNotIn("provider_allowed", cards[0].provider_payload())
        self.assertEqual(self.catalog.revision, cards[0].provider_payload()["catalog_revision"])

    def test_entity_resolution_is_exact_and_ambiguity_is_explicit(self):
        labels = (
            EntityLabel("https://example.test/alice", "Alice", ("A. Example",)),
            EntityLabel("https://example.test/alicia", "Alicia", ("A. Example",)),
        )
        self.assertEqual("resolved", resolve_entity(" alice ", labels).status)
        self.assertEqual("unsupported", resolve_entity("Ali", labels).status)
        self.assertEqual("ambiguous", resolve_entity("a. example", labels).status)

    def test_shape_rag_retries_once_then_delegates_to_engine(self):
        valid = {
            "status": "completed",
            "reason": None,
            "entity_mentions": [
                {"entity_id": "employee", "label": "Priya Shah"},
                {"entity_id": "project", "label": "Project Atlas"},
            ],
            "intent_items": [
                {"id": "boolean", "role": "boolean", "catalog_keys": [], "value": None},
                {
                    "id": "assignment",
                    "role": "relationship",
                    "catalog_keys": [self.catalog.lenses[0].key, self.catalog.properties[0].key],
                    "value": None,
                },
            ],
            "coverage": [
                {"intent_id": "boolean", "disposition": "planned", "atom_ids": ["kind"]},
                {
                    "intent_id": "assignment",
                    "disposition": "planned",
                    "atom_ids": ["entity:employee", "entity:project", "edge:worked"],
                },
            ],
            "plan": self.plan,
        }
        calls = []

        def planner(question, cards, error):
            calls.append(error)
            return PlannerReply({"status": "invalid"} if len(calls) == 1 else valid, "fake-v1")

        rag = ShapeRAG(
            self.engine,
            planner,
            (
                PlannerCard(self.catalog.lenses[0].key, "lens", "staffing", (), "Staffing operations.", ()),
                PlannerCard(self.catalog.properties[0].key, "property", "worked on", (), "Assignments.", ()),
            ),
            (
                EntityLabel("https://example.test/alice", "Alice"),
                EntityLabel("https://example.test/atlas", "Project Atlas"),
            ),
            candidate_limit=2,
        )
        valid["entity_mentions"][0]["label"] = "Alice"
        result = rag.ask("Did Alice work on Project Atlas?")
        self.assertEqual("completed", result.status, result.reason)
        self.assertEqual(2, result.calls)
        self.assertIsNotNone(result.outcome)
        self.assertEqual({"status": "invalid"}, calls[1]["rejected_output"])

        ambiguous = ShapeRAG(
            self.engine,
            lambda question, cards, error: PlannerReply(valid),
            rag.cards,
            (
                EntityLabel("https://example.test/alice", "Alice A", ("Alice",)),
                EntityLabel("https://example.test/alicia", "Alice B", ("Alice",)),
                EntityLabel("https://example.test/atlas", "Project Atlas"),
            ),
            candidate_limit=2,
        ).ask("Did Alice work on Project Atlas?")
        self.assertEqual("ambiguous", ambiguous.status)

        self.assertTrue(ambiguous.internal_coverage_valid)
        self.assertIsNone(ambiguous.outcome)

        invented = copy.deepcopy(valid)
        invented["plan"]["entities"][0]["binding"] = {
            "kind": "iri",
            "value": "https://attacker.example/invented",
        }
        rejected = ShapeRAG(
            self.engine,
            lambda question, cards, error: PlannerReply(invented),
            rag.cards,
            rag.entities,
            candidate_limit=2,
        ).ask("Did Alice work on Project Atlas?")
        self.assertEqual("unsupported", rejected.status)
        self.assertEqual(2, rejected.calls)
        self.assertIn("resolved locally", rejected.reason)

    def test_provider_handles_are_expanded_before_validation(self):
        lens, prop = self.catalog.lenses[0], self.catalog.properties[0]

        def planner(question, cards, error):
            by_kind = {card["kind"]: card for card in cards}
            self.assertEqual({"L", "P"}, {card["key"][0] for card in cards})
            return PlannerReply(
                {
                    "status": "completed",
                    "reason": None,
                    "entity_mentions": [{"entity_id": "employee", "label": "Alice"}],
                    "intent_items": [
                        {"id": "boolean", "role": "boolean", "catalog_keys": [], "value": None},
                        {
                            "id": "employee",
                            "role": "condition",
                            "catalog_keys": [],
                            "value": "Alice",
                        },
                        {
                            "id": "assignment",
                            "role": "relationship",
                            "catalog_keys": [by_kind["property"]["key"]],
                            "value": None,
                        },
                        {
                            "id": "extent",
                            "role": "result_extent",
                            "catalog_keys": [],
                            "value": "complete",
                        },
                    ],
                    "coverage": {
                        "intents": {
                            "boolean": "planned",
                            "employee": "planned",
                            "assignment": "planned",
                            "extent": "planned",
                        },
                        "atoms": {
                            "kind": "boolean",
                            "entity:employee": "employee",
                            "edge:worked": "assignment",
                            "result_extent": "extent",
                        },
                    },
                    "plan": {
                        **self.plan,
                        "catalog_revision": by_kind["lens"]["catalog_revision"],
                        "lenses": [
                            {"id": "staffing", "entity": "employee", "key": by_kind["lens"]["key"]}
                        ],
                        "edges": [
                            {
                                **self.plan["edges"][0],
                                "property_key": by_kind["property"]["key"],
                                "branch_key": by_kind["property"]["branches"][0],
                            }
                        ],
                    },
                }
            )

        result = ShapeRAG(
            self.engine,
            planner,
            (
                PlannerCard(
                    lens.key,
                    "lens",
                    "staffing",
                    (),
                    "Staffing operations.",
                    (("catalog_revision", self.catalog.revision), ("shape_term", lens.shape_term)),
                ),
                PlannerCard(
                    prop.key,
                    "property",
                    "worked on",
                    (),
                    "Assignments.",
                    (
                        ("catalog_revision", self.catalog.revision),
                        ("lens_key", lens.key),
                        ("predicate", prop.predicate_iri),
                        ("inverse", prop.inverse),
                        ("branches", list(prop.branch_keys)),
                    ),
                ),
            ),
            (EntityLabel("https://example.test/alice", "Alice"),),
            candidate_limit=2,
        ).ask("Is any employee assigned to a project?")
        self.assertEqual("completed", result.status, result.reason)
        self.assertEqual(lens.key, result.plan.lenses[0].key)

    def test_result_extent_has_its_own_coverage_atom(self):
        validate_coverage(
            self.plan,
            (
                IntentItem("boolean", "boolean"),
                IntentItem("assignment", "relationship"),
                IntentItem("extent", "result_extent", value="complete"),
            ),
            (
                IntentCoverage("boolean", "planned", ("kind",)),
                IntentCoverage("assignment", "planned", ("edge:worked",)),
                IntentCoverage("extent", "planned", ("result_extent",)),
            ),
        )

    def test_planner_coverage_aliases_are_canonicalized(self):
        raw = {
            "status": "completed",
            "reason": None,
            "entity_mentions": [
                {"entity_id": "employee", "label": "Alice"},
                {"entity_id": "project", "label": "Project Atlas"},
            ],
            "intent_items": [
                {"id": "boolean", "role": "boolean", "catalog_keys": [], "value": None},
                {"id": "extent", "role": "result_extent", "catalog_keys": [], "value": "complete"},
            ],
            "coverage": [
                {
                    "intent_id": "boolean",
                    "disposition": "planned",
                    "atom_ids": ["ask", "edge:worked", "entity:employee", "entity:project"],
                },
                {"intent_id": "extent", "disposition": "planned", "atom_ids": []},
            ],
            "plan": {**self.plan, "kind": "ask"},
        }
        result = ShapeRAG(
            self.engine,
            lambda question, cards, error: PlannerReply(raw),
            (
                PlannerCard(self.catalog.lenses[0].key, "lens", "staffing", (), "Staffing operations.", ()),
                PlannerCard(self.catalog.properties[0].key, "property", "worked on", (), "Assignments.", ()),
            ),
            (
                EntityLabel("https://example.test/alice", "Alice"),
                EntityLabel("https://example.test/atlas", "Project Atlas"),
            ),
            candidate_limit=2,
        ).ask("Does anything exist?")
        self.assertEqual("completed", result.status, result.reason)

    def test_shape_rag_fails_closed_on_missing_coverage(self):
        def planner(question, cards, error):
            return PlannerReply(
                {
                    "status": "unsupported",
                    "reason": "outside algebra",
                    "entity_mentions": [],
                    "intent_items": [
                        {"id": "aggregate", "role": "condition", "catalog_keys": [], "value": "count"}
                    ],
                    "coverage": [],
                    "plan": None,
                }
            )

        rag = ShapeRAG(
            self.engine,
            planner,
            (PlannerCard("staffing", "lens", "staffing", (), "Staffing operations.", ()),),
            (),
            candidate_limit=1,
        )
        result = rag.ask("How many employees are there?")
        self.assertEqual("unsupported", result.status)
        self.assertEqual(2, result.calls)
        self.assertIn("exactly one disposition", result.reason)

        def unavailable(question, cards, error):
            raise ValueError("offline")

        failed = ShapeRAG(
            self.engine,
            unavailable,
            rag.cards,
            (),
            candidate_limit=1,
        ).ask("How many employees are there?")
        self.assertEqual(2, failed.calls)
        self.assertEqual(2, len(failed.raw_replies))
        self.assertEqual("ValueError", failed.raw_replies[0]["request_error"])


if __name__ == "__main__":
    unittest.main()
