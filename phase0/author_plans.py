#!/usr/bin/env python3
"""Resolve hand-authored Phase 0 plan semantics to one pinned catalog artifact."""

from __future__ import annotations

import json
import copy
from pathlib import Path
from typing import Any

from kernel import Catalog, normalize


ROOT = Path(__file__).resolve().parent.parent
CATALOG = Catalog.reload(json.loads((ROOT / "phase0/fixtures/catalog.json").read_text()))
LENSES = {item.shape_term: item for item in CATALOG.lenses}


def iri(value: str) -> dict[str, str]:
    return {"kind": "iri", "value": value}


def literal(value: str, datatype: str | None = None, language: str | None = None) -> dict[str, Any]:
    return {"kind": "literal", "value": value, "datatype": datatype, "language": language}


def lens(use_id: str, entity: str, shape: str) -> dict[str, str]:
    return {"id": use_id, "entity": entity, "key": LENSES[shape].key}


def selector(use_id: str, entity: str, shape: str, kind: str = "direct_type") -> dict[str, str]:
    definition = next(
        item for item in CATALOG.selectors
        if item.lens_key == LENSES[shape].key and item.kind == kind
    )
    return {"id": use_id, "entity": entity, "key": definition.key}


def property_key(shape: str, predicate: str, inverse: bool = False) -> tuple[str, str]:
    definition = next(
        item for item in CATALOG.properties
        if item.lens_key == LENSES[shape].key
        and item.predicate_iri == predicate
        and item.inverse == inverse
    )
    return definition.key, definition.branch_keys[0]


def edge(atom_id: str, use_id: str, shape: str, predicate: str, target: str, inverse: bool = False) -> dict[str, str]:
    key, branch = property_key(shape, predicate, inverse)
    return {"id": atom_id, "source_lens": use_id, "property_key": key, "branch_key": branch, "target_entity": target}


def eq(atom_id: str, use_id: str, shape: str, predicate: str, value: dict[str, Any], inverse: bool = False) -> dict[str, Any]:
    key, branch = property_key(shape, predicate, inverse)
    return {"kind": "eq", "id": atom_id, "lens": use_id, "property_key": key, "branch_key": branch, "value": value}


def node(projection_id: str, entity: str) -> dict[str, str]:
    return {"kind": "node", "id": projection_id, "entity": entity}


def field(projection_id: str, use_id: str, shape: str, predicate: str) -> dict[str, Any]:
    key, branch = property_key(shape, predicate)
    return {"kind": "field", "id": projection_id, "lens": use_id, "property_key": key, "branch_key": branch, "required": True}


def plan(kind: str, entities: list[tuple[str, dict[str, Any] | None]], selectors: list[dict[str, Any]], lenses: list[dict[str, Any]], edges: list[dict[str, Any]], filters: list[dict[str, Any]], projections: list[dict[str, Any]] = ()) -> dict[str, Any]:
    raw = {
        "kind": kind,
        "catalog_revision": CATALOG.revision,
        "entities": [{"id": entity_id, "binding": binding} for entity_id, binding in entities],
        "selectors": selectors,
        "lenses": lenses,
        "edges": edges,
        "filters": filters,
        "projections": list(projections),
    }
    normalize(raw, CATALOG)
    return raw


S = "https://example.org/staffing/"
OPS = "https://example.test/ops/"
R = "https://catalog.example.org/ns/"
SEM = "https://example.test/semantic/"
XSD = "http://www.w3.org/2001/XMLSchema#"

ES, ED, PS, SK = S + "EmployeeStaffingShape", S + "EmployeeDirectoryShape", S + "ProjectStaffingShape", S + "SkillShape"
OS, OT, OD = OPS + "ServiceShape", OPS + "TeamShape", OPS + "DeploymentShape"
RP, RR, RG = R + "PublicationShape", R + "ResearcherShape", R + "GrantShape"
SS, ST, SI = SEM + "ServiceShape", SEM + "TeamShape", SEM + "IdentityShape"
SINC, SOP, SDIR = SEM + "IncidentFocusShape", SEM + "OperationsPersonShape", SEM + "DirectoryPersonShape"


def authored_plans() -> dict[str, dict[str, Any]]:
    plans: dict[str, dict[str, Any]] = {}
    def add(name: str, value: dict[str, Any]) -> None:
        plans[name] = value

    add("staffing-q01", plan("select", [("employee", None), ("project", iri(S+"project-atlas")), ("skill", iri(S+"skill-ai"))], [selector("employee-pop", "employee", ES)], [lens("staffing", "employee", ES), lens("directory", "employee", ED)], [edge("worked", "staffing", ES, S+"workedOn", "project"), edge("expertise", "staffing", ES, S+"expertise", "skill")], [], [node("employee", "employee"), field("name", "directory", ED, S+"displayName")]))
    add("staffing-q02", plan("select", [("employee", None), ("project", iri(S+"project-beacon"))], [selector("employee-pop", "employee", ES)], [lens("staffing", "employee", ES), lens("directory", "employee", ED)], [edge("worked", "staffing", ES, S+"workedOn", "project")], [], [node("employee", "employee"), field("name", "directory", ED, S+"displayName")]))
    add("staffing-q03", plan("select", [("employee", None), ("skill", iri(S+"skill-kubernetes"))], [selector("employee-pop", "employee", ES)], [lens("staffing", "employee", ES), lens("directory", "employee", ED)], [edge("expertise", "staffing", ES, S+"expertise", "skill")], [], [node("employee", "employee"), field("name", "directory", ED, S+"displayName")]))
    add("staffing-q04", plan("select", [("project", None), ("employee", iri(S+"employee-alice"))], [selector("project-pop", "project", PS)], [lens("projects", "project", PS)], [edge("worked-inverse", "projects", PS, S+"workedOn", "employee", True)], [], [node("project", "project"), field("title", "projects", PS, S+"title")]))
    add("staffing-q05", plan("select", [("employee", iri(S+"employee-omar")), ("skill", None)], [], [lens("staffing", "employee", ES), lens("skill-view", "skill", SK)], [edge("expertise", "staffing", ES, S+"expertise", "skill")], [], [node("skill", "skill"), field("label", "skill-view", SK, S+"label")]))
    add("staffing-q06", plan("ask", [("employee", iri(S+"employee-priya")), ("project", iri(S+"project-atlas"))], [], [lens("staffing", "employee", ES)], [edge("worked", "staffing", ES, S+"workedOn", "project")], []))
    add("staffing-q07", plan("select", [("employee", None), ("cloud", iri(S+"skill-cloud-architecture")), ("security", iri(S+"skill-cybersecurity"))], [selector("employee-pop", "employee", ES)], [lens("staffing", "employee", ES), lens("directory", "employee", ED)], [edge("cloud", "staffing", ES, S+"expertise", "cloud"), edge("security", "staffing", ES, S+"expertise", "security")], [], [node("employee", "employee"), field("name", "directory", ED, S+"displayName")]))

    add("ops-q01", plan("select", [("service", iri(OPS+"PaymentsApi")), ("team", None), ("contact", None)], [], [lens("service-view", "service", OS), lens("team-view", "team", OT)], [edge("owner", "service-view", OS, OPS+"ownedBy", "team"), edge("contact", "team-view", OT, OPS+"onCallContact", "contact")], [], [node("team", "team"), node("contact", "contact")]))
    add("ops-q02", plan("select", [("service", None), ("team", iri(OPS+"PaymentsTeam"))], [selector("service-pop", "service", OS)], [lens("service-view", "service", OS)], [edge("owner", "service-view", OS, OPS+"ownedBy", "team")], [], [node("service", "service")]))
    add("ops-q03", plan("select", [("service", iri(OPS+"CheckoutApi")), ("runbook", None)], [], [lens("service-view", "service", OS)], [edge("runbook", "service-view", OS, OPS+"runbook", "runbook")], [], [node("runbook", "runbook")]))
    add("ops-q04", plan("select", [("service", None), ("dependency", iri(OPS+"PaymentsApi"))], [selector("service-pop", "service", OS)], [lens("service-view", "service", OS)], [edge("dependency", "service-view", OS, OPS+"dependsOn", "dependency")], [], [node("service", "service")]))
    add("ops-q05", plan("select", [("service", None), ("team", iri(OPS+"CommerceTeam")), ("deployment", None), ("environment", iri(OPS+"Production"))], [selector("service-pop", "service", OS)], [lens("service-view", "service", OS), lens("deployment-view", "deployment", OD)], [edge("owner", "service-view", OS, OPS+"ownedBy", "team"), edge("deployment", "service-view", OS, OPS+"hasDeployment", "deployment"), edge("environment", "deployment-view", OD, OPS+"environment", "environment")], [], [node("service", "service"), node("deployment", "deployment")]))
    add("ops-q06", plan("select", [("service", None), ("deployment", iri(OPS+"PaymentsProduction")), ("team", None), ("contact", None)], [selector("service-pop", "service", OS)], [lens("service-view", "service", OS), lens("team-view", "team", OT)], [edge("deployment", "service-view", OS, OPS+"hasDeployment", "deployment"), edge("owner", "service-view", OS, OPS+"ownedBy", "team"), edge("contact", "team-view", OT, OPS+"onCallContact", "contact")], [], [node("service", "service"), node("team", "team"), node("contact", "contact")]))
    add("ops-q07", plan("ask", [("service", iri(OPS+"Ledger")), ("team", iri(OPS+"FinanceTeam"))], [], [lens("service-view", "service", OS)], [edge("owner", "service-view", OS, OPS+"ownedBy", "team")], []))

    add("research-q01", plan("select", [("publication", None), ("researcher", iri(R+"lee")), ("venue", None)], [selector("publication-pop", "publication", RP)], [lens("publication-view", "publication", RP)], [edge("contributor", "publication-view", RP, R+"contributor", "researcher"), edge("venue", "publication-view", RP, R+"publishedIn", "venue")], [], [node("publication", "publication"), field("title", "publication-view", RP, R+"title"), field("year", "publication-view", RP, R+"publicationYear"), node("venue", "venue")]))
    add("research-q02", plan("select", [("publication", None), ("grant", None), ("contributor", None)], [selector("publication-pop", "publication", RP)], [lens("publication-view", "publication", RP), lens("grant-view", "grant", RG)], [edge("funding", "publication-view", RP, R+"fundedBy", "grant"), edge("contributor", "publication-view", RP, R+"contributor", "contributor")], [eq("grant-number", "grant-view", RG, R+"grantNumber", literal("NORD-42"))], [node("publication", "publication"), field("title", "publication-view", RP, R+"title"), field("year", "publication-view", RP, R+"publicationYear"), node("contributor", "contributor")]))
    add("research-q03", plan("select", [("publication", None), ("venue", iri(R+"journal-a")), ("researcher", None), ("department", None)], [selector("publication-pop", "publication", RP)], [lens("publication-view", "publication", RP), lens("researcher-view", "researcher", RR)], [edge("venue", "publication-view", RP, R+"publishedIn", "venue"), edge("contributor", "publication-view", RP, R+"contributor", "researcher"), edge("department", "researcher-view", RR, R+"memberOf", "department")], [], [node("researcher", "researcher"), field("name", "researcher-view", RR, R+"displayName"), node("department", "department"), node("publication", "publication"), field("title", "publication-view", RP, R+"title")]))
    add("research-q05", plan("select", [("publication", None), ("dataset", iri(R+"coast-data")), ("contributor", None)], [selector("publication-pop", "publication", RP)], [lens("publication-view", "publication", RP)], [edge("dataset", "publication-view", RP, R+"usesDataset", "dataset"), edge("contributor", "publication-view", RP, R+"contributor", "contributor")], [], [node("publication", "publication"), field("title", "publication-view", RP, R+"title"), field("year", "publication-view", RP, R+"publicationYear"), node("contributor", "contributor")]))

    core = plan("select", [("service", None), ("team", iri(SEM+"PaymentsTeam"))], [selector("service-pop", "service", SS)], [lens("service-view", "service", SS)], [edge("owner-edge", "service-view", SS, SEM+"ownedBy", "team")], [eq("owner-filter", "service-view", SS, SEM+"ownedBy", iri(SEM+"PaymentsTeam"))], [node("service", "service")])
    add("semantic-core-select", core)
    equivalent = copy.deepcopy(core)
    equivalent["entities"] = [
        {"id": "bound-team", "binding": iri(SEM+"PaymentsTeam")},
        {"id": "root-service", "binding": None},
    ]
    equivalent["selectors"] = [{**equivalent["selectors"][0], "id": "population", "entity": "root-service"}]
    equivalent["lenses"] = [{**equivalent["lenses"][0], "id": "view", "entity": "root-service"}]
    equivalent["edges"] = [{**equivalent["edges"][0], "id": "relationship", "source_lens": "view", "target_entity": "bound-team"}]
    equivalent["filters"] = [{**equivalent["filters"][0], "id": "identity", "lens": "view"}]
    equivalent["projections"] = [{**equivalent["projections"][0], "id": "answer", "entity": "root-service"}]
    normalize(equivalent, CATALOG)
    add("semantic-normalization-equivalent-alt", equivalent)
    near_miss = copy.deepcopy(core)
    near_miss["entities"][1]["binding"] = iri(SEM+"OtherTeam")
    normalize(near_miss, CATALOG)
    add("semantic-normalization-near-miss", near_miss)
    add("semantic-ask-true", plan("ask", [("service", iri(SEM+"PaymentsApi")), ("team", iri(SEM+"PaymentsTeam"))], [], [lens("service-view", "service", SS)], [edge("owner", "service-view", SS, SEM+"ownedBy", "team")], []))
    add("semantic-ask-false", plan("ask", [("service", iri(SEM+"EmptyService")), ("team", iri(SEM+"PaymentsTeam"))], [], [lens("service-view", "service", SS)], [edge("owner", "service-view", SS, SEM+"ownedBy", "team")], []))
    add("semantic-select-empty", plan("select", [("service", None), ("team", iri(SEM+"MissingTeam"))], [selector("service-pop", "service", SS)], [lens("service-view", "service", SS)], [edge("owner", "service-view", SS, SEM+"ownedBy", "team")], [], [node("service", "service")]))
    add("semantic-target-node", plan("select", [("service", None), ("team", None)], [selector("incident-target", "service", SINC, "target_nodes")], [lens("incident-view", "service", SINC)], [edge("owner", "incident-view", SINC, SEM+"ownedBy", "team")], [], [node("service", "service"), node("team", "team")]))
    add("semantic-inverse", plan("select", [("team", None), ("service", None)], [selector("team-pop", "team", ST)], [lens("team-view", "team", ST)], [edge("owned-service", "team-view", ST, SEM+"ownedBy", "service", True)], [], [node("team", "team"), node("service", "service")]))
    for name, predicate, value in (
        ("iri-match", SEM+"iriTerm", iri(SEM+"ExactIri")),
        ("iri-miss", SEM+"iriTerm", iri(SEM+"OtherIri")),
        ("datatype-string", SEM+"typedTerm", literal("01", XSD+"string")),
        ("datatype-integer", SEM+"typedTerm", literal("01", XSD+"integer")),
        ("datatype-miss", SEM+"typedTerm", literal("01", XSD+"decimal")),
        ("lexical-leading-zero", SEM+"lexicalTerm", literal("01", XSD+"integer")),
        ("lexical-one", SEM+"lexicalTerm", literal("1", XSD+"integer")),
        ("language-en", SEM+"languageTerm", literal("colour", language="en")),
        ("language-fr", SEM+"languageTerm", literal("colour", language="fr")),
        ("language-miss", SEM+"languageTerm", literal("colour", language="de")),
    ):
        add("semantic-identity-" + name, plan("select", [("probe", None)], [selector("probe-target", "probe", SI, "target_nodes")], [lens("identity-view", "probe", SI)], [], [eq("identity", "identity-view", SI, predicate, value)], [node("probe", "probe")]))
    add("semantic-multi-lens", plan("select", [("person", None)], [selector("person-pop", "person", SOP)], [lens("operations-view", "person", SOP), lens("directory-view", "person", SDIR)], [], [eq("membership", "operations-view", SOP, SEM+"memberOf", iri(SEM+"PaymentsTeam"))], [node("person", "person"), field("name", "directory-view", SDIR, SEM+"displayName")]))
    return plans


if __name__ == "__main__":
    print(json.dumps(authored_plans(), indent=2, sort_keys=True))
