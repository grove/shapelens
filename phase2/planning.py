"""Experimental graph-only planning harness; not part of the public package."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
import re
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shapelens import Plan, QueryOutcome, ShapeQueryEngine, Term


class PlanningError(ValueError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanningError(f"{name} must be a non-empty string")
    return value.strip()


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _map_strings(value: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [_map_strings(item, transform) for item in value]
    if isinstance(value, Mapping):
        return {key: _map_strings(item, transform) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class PlannerCard:
    key: str
    kind: str
    label: str
    aliases: tuple[str, ...]
    description: str
    fields: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if self.kind not in {"lens", "selector", "property"}:
            raise PlanningError("planner card kind must be lens, selector, or property")
        _text(self.key, "planner card key")
        _text(self.label, "planner card label")
        if not isinstance(self.aliases, tuple) or any(not isinstance(x, str) or not x for x in self.aliases):
            raise PlanningError("planner card aliases must be non-empty strings")
        if not isinstance(self.fields, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str)
            for item in self.fields
        ):
            raise PlanningError("planner card fields must be key/value pairs")

    def provider_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "aliases": list(self.aliases),
            "description": self.description,
            **dict(self.fields),
        }


@dataclass(frozen=True)
class EntityLabel:
    iri: str
    label: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        Term.load({"kind": "iri", "value": self.iri})
        _text(self.label, "entity label")
        if not isinstance(self.aliases, tuple) or any(not isinstance(x, str) or not x for x in self.aliases):
            raise PlanningError("entity aliases must be non-empty strings")


@dataclass(frozen=True)
class EntityResolution:
    status: str
    iris: tuple[str, ...]


@dataclass(frozen=True)
class EntityMentionResolution:
    entity_id: str
    label: str
    status: str
    iris: tuple[str, ...]


def resolve_entity(mention: str, entities: Iterable[EntityLabel]) -> EntityResolution:
    wanted = _normalize(_text(mention, "entity mention"))
    matches = tuple(
        sorted(
            {
                entity.iri
                for entity in entities
                if wanted in {_normalize(entity.label), *(_normalize(alias) for alias in entity.aliases)}
            }
        )
    )
    return EntityResolution("resolved" if len(matches) == 1 else "unsupported" if not matches else "ambiguous", matches)


def cards_from_catalog(catalog: Any, annotations: Mapping[str, Mapping[str, Any]]) -> tuple[PlannerCard, ...]:
    """Serialize only explicitly annotated, executable catalog material."""
    cards: list[PlannerCard] = []
    for kind, items in (("lens", catalog.lenses), ("selector", catalog.selectors), ("property", catalog.properties)):
        for item in items:
            note = annotations.get(item.key)
            if (
                not note
                or note.get("provider_allowed") is not True
                or not item.trusted
                or not getattr(item, "qualified", True)
            ):
                continue
            aliases = note.get("aliases", ())
            if not isinstance(aliases, (list, tuple)):
                raise PlanningError("planner card aliases must be an array")
            fields: dict[str, Any]
            if kind == "lens":
                fields = {"catalog_revision": catalog.revision, "shape_term": item.shape_term}
            elif kind == "selector":
                fields = {
                    "catalog_revision": catalog.revision,
                    "lens_key": item.lens_key,
                    "classes": list(item.classes),
                    "targets": list(item.target_iris),
                }
            else:
                fields = {
                    "catalog_revision": catalog.revision,
                    "lens_key": item.lens_key,
                    "predicate": item.predicate_iri,
                    "inverse": item.inverse,
                    "branches": [branch.key for branch in item.branches],
                }
            cards.append(
                PlannerCard(
                    item.key,
                    kind,
                    _text(note.get("label"), "planner card label"),
                    tuple(aliases),
                    _text(note.get("description"), "planner card description"),
                    tuple(fields.items()),
                )
            )
    return tuple(sorted(cards, key=lambda card: card.key))


def retrieve_cards(question: str, cards: Iterable[PlannerCard], limit: int) -> tuple[PlannerCard, ...]:
    if type(limit) is not int or limit <= 0:
        raise PlanningError("candidate limit must be a positive integer")
    stopwords = {"and", "are", "both", "during", "for", "from", "has", "have", "how", "into", "our", "still", "that", "the", "their", "them", "they", "this", "what", "when", "where", "which", "who", "with"}
    words = {word for word in _normalize(_text(question, "question")).split() if len(word) > 2 and word not in stopwords}
    scored = []
    for card in cards:
        card_words = {
            word
            for word in _normalize(" ".join((card.label, *card.aliases, card.description))).split()
            if len(word) > 2 and word not in stopwords
        }
        group = card.key if card.kind == "lens" else dict(card.fields).get("lens_key", card.key)
        scored.append((len(words & card_words), group, card))
    group_scores = Counter()
    for score, group, _ in scored:
        group_scores[group] += score
    groups: dict[str, list[tuple[int, PlannerCard]]] = {}
    for score, group, card in scored:
        groups.setdefault(group, []).append((score, card))
    ranked = []
    for group in sorted(groups, key=lambda key: (-group_scores[key], key)):
        ranked.extend(card for _, card in sorted(groups[group], key=lambda row: (-row[0], row[1].key)))
    return tuple(ranked[:limit])


@dataclass(frozen=True)
class IntentItem:
    id: str
    role: str
    catalog_keys: tuple[str, ...] = ()
    value: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "intent item ID")
        if self.role not in {"population", "relationship", "condition", "projection", "boolean", "result_extent"}:
            raise PlanningError("invalid intent role")
        if not isinstance(self.catalog_keys, tuple) or any(not isinstance(x, str) or not x for x in self.catalog_keys):
            raise PlanningError("intent catalog keys must be non-empty strings")
        if self.value is not None and (not isinstance(self.value, str) or not self.value):
            raise PlanningError("intent value must be null or a non-empty string")


@dataclass(frozen=True)
class IntentCoverage:
    intent_id: str
    disposition: str
    atom_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.intent_id, "coverage intent ID")
        if self.disposition not in {"planned", "unsupported", "ambiguous"}:
            raise PlanningError("invalid intent disposition")
        if not isinstance(self.atom_ids, tuple) or any(not isinstance(x, str) or not x for x in self.atom_ids):
            raise PlanningError("coverage atom IDs must be non-empty strings")
        if (self.disposition == "planned") != bool(self.atom_ids):
            raise PlanningError("only planned coverage has atom IDs")


def _plan_atom_ids(plan: Plan) -> frozenset[str]:
    atoms = {"kind"}
    atoms.update(f"entity:{item.id}" for item in plan.entities if item.bound is not None)
    for name in ("selectors", "edges", "filters", "projections"):
        atoms.update(f"{name[:-1]}:{item.id}" for item in getattr(plan, name))
    return frozenset(atoms)


def _raw_plan_atom_ids(plan: Mapping[str, Any]) -> frozenset[str]:
    atoms = {"kind"}
    atoms.update(
        f"entity:{item.get('id')}"
        for item in plan.get("entities", ())
        if isinstance(item, Mapping) and item.get("binding") is not None
    )
    for name in ("selectors", "edges", "filters", "projections"):
        atoms.update(
            f"{name[:-1]}:{item.get('id')}"
            for item in plan.get(name, ())
            if isinstance(item, Mapping)
        )
    return frozenset(atoms)


def validate_coverage(
    plan: Plan | Mapping[str, Any] | None,
    intent_items: Iterable[IntentItem],
    coverage: Iterable[IntentCoverage],
) -> tuple[IntentItem, ...]:
    intents, links = tuple(intent_items), tuple(coverage)
    intent_ids = [item.id for item in intents]
    covered_ids = [item.intent_id for item in links]
    if not intents or len(intent_ids) != len(set(intent_ids)) or sorted(intent_ids) != sorted(covered_ids):
        raise PlanningError("every unique material intent item must have exactly one disposition")
    planned_atoms = [atom for link in links for atom in link.atom_ids]
    if len(planned_atoms) != len(set(planned_atoms)):
        raise PlanningError("every planner atom must have exactly one intent source")
    expected = (
        _plan_atom_ids(plan)
        if isinstance(plan, Plan)
        else _raw_plan_atom_ids(plan)
        if isinstance(plan, Mapping)
        else frozenset()
    )
    if any(item.role == "result_extent" for item in intents):
        expected = expected | {"result_extent"}
    if frozenset(planned_atoms) != expected:
        raise PlanningError(
            f"intent coverage must cover planner atoms {sorted(expected)}; got {sorted(planned_atoms)}"
        )
    if plan is not None and any(link.disposition != "planned" for link in links):
        raise PlanningError("completed plans cannot contain unresolved intent")
    return intents


@dataclass(frozen=True)
class PlannerReply:
    value: Mapping[str, Any]
    model: str = "fake"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.value, Mapping):
            raise PlanningError("planner reply must contain a JSON object")
        _text(self.model, "planner model")
        if (
            type(self.input_tokens) is not int
            or self.input_tokens < 0
            or type(self.output_tokens) is not int
            or self.output_tokens < 0
        ):
            raise PlanningError("planner token counts must be non-negative integers")
        if (
            type(self.latency_seconds) not in {int, float}
            or not math.isfinite(self.latency_seconds)
            or self.latency_seconds < 0
        ):
            raise PlanningError("planner latency must be finite and non-negative")


Planner = Callable[[str, tuple[dict[str, Any], ...], Mapping[str, Any] | None], PlannerReply]


@dataclass(frozen=True)
class PlannedQuery:
    status: str
    plan: Plan | None
    outcome: QueryOutcome | None
    intent_items: tuple[IntentItem, ...]
    coverage: tuple[IntentCoverage, ...]
    entity_resolutions: tuple[EntityMentionResolution, ...]
    candidate_card_keys: tuple[str, ...]
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    reason: str | None = None
    internal_coverage_valid: bool = True
    raw_replies: tuple[Mapping[str, Any], ...] = ()


class ShapeRAG:
    def __init__(
        self,
        engine: ShapeQueryEngine,
        planner: Planner,
        cards: Iterable[PlannerCard],
        entities: Iterable[EntityLabel],
        *,
        candidate_limit: int = 24,
    ) -> None:
        if not isinstance(engine, ShapeQueryEngine) or not callable(planner):
            raise PlanningError("ShapeRAG requires a deterministic engine and planner")
        self.engine = engine
        self.planner = planner
        self.cards = tuple(cards)
        self.entities = tuple(entities)
        self.candidate_limit = candidate_limit

    def ask(self, question: str) -> PlannedQuery:
        candidates = retrieve_cards(question, self.cards, self.candidate_limit)
        aliases: dict[str, str] = {}

        def compact(value: str) -> str:
            if not value.startswith("sha256:"):
                return value
            for marker, prefix in ((":lens:", "L"), (":selector:", "S"), (":property:", "P"), (":branch:", "B")):
                if marker in value:
                    return aliases.setdefault(value, prefix + value.rsplit(marker, 1)[1].replace(":", "_"))
            return aliases.setdefault(value, "R")

        payload = tuple(_map_strings(card.provider_payload(), compact) for card in candidates)
        expanded = {short: full for full, short in aliases.items()}
        error: Mapping[str, Any] | None = None
        replies: list[PlannerReply] = []
        for _ in range(2):
            reply_count = len(replies)
            try:
                reply = self.planner(question, payload, error)
                if not isinstance(reply, PlannerReply):
                    raise PlanningError("planner must return a PlannerReply")
                replies.append(reply)
                return self._accept(
                    _map_strings(reply.value, lambda value: expanded.get(value, value)),
                    candidates,
                    replies,
                )
            except (PlanningError, AttributeError, KeyError, TypeError, ValueError) as exc:
                if len(replies) == reply_count:
                    replies.append(
                        PlannerReply(
                            {"request_error": type(exc).__name__},
                            replies[-1].model if replies else "unknown",
                        )
                    )
                error = {"message": str(exc), "rejected_output": replies[-1].value}
                last_error = str(exc)
        return self._result(
            "unsupported",
            candidates,
            replies,
            reason=f"planner output rejected: {last_error}",
            internal_coverage_valid=False,
        )

    def _accept(
        self,
        raw: Mapping[str, Any],
        candidates: tuple[PlannerCard, ...],
        replies: list[PlannerReply],
    ) -> PlannedQuery:
        if not isinstance(raw, Mapping):
            raise PlanningError("planner output must be an object")
        fields = {
            "status",
            "reason",
            "entity_mentions",
            "intent_items",
            "coverage",
            "plan",
        }
        if set(raw) != fields:
            raise PlanningError("planner output must contain exactly the required fields")
        status = raw.get("status")
        if status not in {"completed", "unsupported", "ambiguous"}:
            raise PlanningError("planner status must be completed, unsupported, or ambiguous")
        if (status == "completed") != (raw.get("reason") is None):
            raise PlanningError("only completed output has a null reason")
        if status != "completed" and raw.get("plan") is not None:
            raise PlanningError("non-completed output cannot contain a plan")
        intents = tuple(
            IntentItem(
                _text(item.get("id"), "intent ID"),
                item.get("role"),
                tuple(item.get("catalog_keys", ())),
                item.get("value"),
            )
            for item in raw.get("intent_items", ())
        )
        extent_ids = {item.id for item in intents if item.role == "result_extent"}
        coverage_raw = raw.get("coverage", ())
        if isinstance(coverage_raw, Mapping):
            if set(coverage_raw) != {"intents", "atoms"}:
                raise PlanningError("coverage must contain exactly intents and atoms")
            dispositions, sources = coverage_raw["intents"], coverage_raw["atoms"]
            if not isinstance(dispositions, Mapping) or not isinstance(sources, Mapping):
                raise PlanningError("coverage intents and atoms must be objects")
            if any(owner not in dispositions for owner in sources.values()):
                raise PlanningError("coverage atom references an unknown intent")
            coverage_raw = [
                {
                    "intent_id": intent_id,
                    "disposition": disposition,
                    "atom_ids": [atom for atom, owner in sources.items() if owner == intent_id],
                }
                for intent_id, disposition in dispositions.items()
            ]
        coverage = tuple(
            IntentCoverage(
                intent_id := _text(item.get("intent_id"), "coverage intent ID"),
                item.get("disposition"),
                (
                    ("result_extent",)
                    if intent_id in extent_ids
                    and item.get("disposition") == "planned"
                    and not item.get("atom_ids")
                    else tuple(
                        "kind" if atom in {"select", "ask"} else atom
                        for atom in item.get("atom_ids", ())
                    )
                ),
            )
            for item in coverage_raw
        )
        if status == "completed" and "kind" not in {atom for item in coverage for atom in item.atom_ids}:
            owner = next(
                (item.id for item in intents if item.role == "boolean"),
                next((item.id for item in intents if item.role == "result_extent"), None),
            )
            if owner is not None:
                coverage = tuple(
                    IntentCoverage(
                        item.intent_id,
                        item.disposition,
                        item.atom_ids + (("kind",) if item.intent_id == owner else ()),
                    )
                    for item in coverage
                )
        mentions = raw.get("entity_mentions", ())
        if not isinstance(mentions, list) or any(
            not isinstance(mention, Mapping)
            or not isinstance(mention.get("entity_id"), str)
            or not isinstance(mention.get("label"), str)
            for mention in mentions
        ):
            raise PlanningError("entity_mentions must contain entity IDs and labels")
        if len({mention["entity_id"] for mention in mentions}) != len(mentions):
            raise PlanningError("entity mention IDs must be unique")
        resolutions = tuple(
            EntityMentionResolution(
                mention["entity_id"],
                mention["label"],
                resolution.status,
                resolution.iris,
            )
            for mention in mentions
            for resolution in (resolve_entity(mention["label"], self.entities),)
        )
        allowed = {card.key for card in candidates}
        if any(key not in allowed for intent in intents for key in intent.catalog_keys):
            raise PlanningError("intent references a card outside candidate context")
        if status != "completed":
            validate_coverage(None, intents, coverage)
            resolved_status = (
                "ambiguous"
                if any(item.status == "ambiguous" for item in resolutions)
                else "unsupported"
                if any(item.status == "unsupported" for item in resolutions)
                else status
            )
            return self._result(
                resolved_status,
                candidates,
                replies,
                intents,
                coverage,
                entity_resolutions=resolutions,
                reason=_text(raw.get("reason"), "reason"),
            )
        plan_raw = raw.get("plan")
        if not isinstance(plan_raw, Mapping):
            raise PlanningError("completed output requires a plan")
        plan_raw = json.loads(json.dumps(plan_raw))
        entities = plan_raw.get("entities")
        if not isinstance(entities, list) or any(not isinstance(item, Mapping) for item in entities):
            raise PlanningError("plan entities must be an array of objects")
        if any(item.get("binding") is not None for item in entities):
            raise PlanningError("planner entity bindings must be resolved locally")
        used = {
            item["key"] for group in ("lenses", "selectors") for item in plan_raw.get(group, ())
        }
        used.update(
            item["property_key"]
            for group in ("edges", "filters", "projections")
            for item in plan_raw.get(group, ())
            if "property_key" in item
        )
        if not used <= allowed:
            raise PlanningError("plan references a card outside candidate context")
        by_id = {item.get("id"): item for item in entities if isinstance(item, dict)}
        coverage_plan = json.loads(json.dumps(plan_raw))
        coverage_entities = {
            item.get("id"): item for item in coverage_plan["entities"] if isinstance(item, dict)
        }
        for mention in mentions:
            if not isinstance(mention, Mapping) or mention.get("entity_id") not in coverage_entities:
                raise PlanningError("entity mention references an unknown plan entity")
            coverage_entities[mention["entity_id"]]["binding"] = {
                "kind": "iri",
                "value": f"urn:shapelens:entity-mention:{mention['entity_id']}",
            }
        validate_coverage(coverage_plan, intents, coverage)
        for mention, resolution in zip(mentions, resolutions, strict=True):
            if resolution.status != "resolved":
                return self._result(
                    resolution.status,
                    candidates,
                    replies,
                    intents,
                    coverage,
                    entity_resolutions=resolutions,
                    reason=f"{resolution.status} entity: {mention['label']}",
                )
            by_id[mention["entity_id"]]["binding"] = {"kind": "iri", "value": resolution.iris[0]}
        try:
            plan = self.engine.validate_plan(plan_raw)
        except Exception as exc:
            raise PlanningError(f"plan rejected: {exc}") from exc
        return self._result(
            "completed",
            candidates,
            replies,
            intents,
            coverage,
            plan,
            self.engine.execute_plan(plan),
            entity_resolutions=resolutions,
        )

    def _result(
        self,
        status: str,
        candidates: tuple[PlannerCard, ...],
        replies: list[PlannerReply],
        intents: tuple[IntentItem, ...] = (),
        coverage: tuple[IntentCoverage, ...] = (),
        plan: Plan | None = None,
        outcome: QueryOutcome | None = None,
        reason: str | None = None,
        internal_coverage_valid: bool = True,
        entity_resolutions: tuple[EntityMentionResolution, ...] = (),
    ) -> PlannedQuery:
        return PlannedQuery(
            status,
            plan,
            outcome,
            intents,
            coverage,
            entity_resolutions,
            tuple(card.key for card in candidates),
            replies[-1].model if replies else "unknown",
            len(replies),
            sum(reply.input_tokens for reply in replies),
            sum(reply.output_tokens for reply in replies),
            sum(reply.latency_seconds for reply in replies),
            reason,
            internal_coverage_valid,
            tuple(reply.value for reply in replies),
        )


class OpenAIPlanner:
    """Minimal Chat Completions structured-output adapter."""

    def __init__(
        self,
        api_key: str,
        model: str,
        prompt: str,
        *,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
        timeout: float = 10.0,
        reasoning_effort: str = "none",
    ) -> None:
        self.api_key = _text(api_key, "API key")
        self.model = _text(model, "model")
        self.prompt = _text(prompt, "prompt")
        self.endpoint = _text(endpoint, "endpoint")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
            raise PlanningError("planner timeout must be finite and positive")
        if reasoning_effort not in {"none", "low", "medium", "high"}:
            raise PlanningError("invalid reasoning effort")
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort

    def __call__(
        self,
        question: str,
        cards: tuple[dict[str, Any], ...],
        error: Mapping[str, Any] | None,
    ) -> PlannerReply:
        content = json.dumps({"question": question, "cards": cards, "previous_error": error}, separators=(",", ":"))
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": content},
                ],
                "response_format": {"type": "json_object"},
                "reasoning_effort": self.reasoning_effort,
            }
        ).encode()
        request = Request(
            self.endpoint,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise PlanningError(f"planner request failed: {type(exc).__name__}") from exc
        try:
            value = json.loads(result["choices"][0]["message"]["content"])
            usage = result.get("usage", {})
            return PlannerReply(
                value,
                result.get("model", self.model),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                time.monotonic() - started,
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise PlanningError("planner response was not a JSON object") from exc


__all__ = [
    "EntityLabel",
    "EntityMentionResolution",
    "EntityResolution",
    "IntentCoverage",
    "IntentItem",
    "OpenAIPlanner",
    "PlannedQuery",
    "PlannerCard",
    "PlannerReply",
    "PlanningError",
    "ShapeRAG",
    "cards_from_catalog",
    "resolve_entity",
    "retrieve_cards",
    "validate_coverage",
]
