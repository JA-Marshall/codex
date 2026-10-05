"""Versioned intent requirements and authorized owner facts, kept host-side."""

from dataclasses import dataclass
import json
import re

from task_registry import IDENTIFIER, read_json, relative_path


@dataclass(frozen=True)
class TaskSpecV2:
    requirements: tuple
    owner_facts: tuple
    milestones: tuple
    changes: tuple

    @classmethod
    def load(cls, root, manifest):
        policy = read_json(root / "private/policy.json")
        if manifest.get("track") not in ("A", "B") or manifest.get("pressure") not in (
            "intent",
            "ambiguity",
            "change",
            "compatibility",
            "integration",
            "review",
        ):
            raise ValueError("v2 task requires a track and declared pressure")
        cases = read_json(root / "private/cases.json")
        case_ids = {case["id"] for case in cases}
        requirements = policy.get("requirements")
        if not isinstance(requirements, list) or not 1 <= len(requirements) <= 32:
            raise ValueError("v2 task requires bounded stable requirements")
        ids = set()
        for requirement in requirements:
            identity = requirement.get("id", "")
            evidence = requirement.get("cases")
            if (
                not IDENTIFIER.fullmatch(identity)
                or identity in ids
                or type(requirement.get("critical")) is not bool
                or not isinstance(evidence, list)
                or not evidence
                or not set(evidence) <= case_ids
            ):
                raise ValueError(
                    "invalid requirement identity or acceptance case mapping"
                )
            ids.add(identity)
        if not any(requirement["critical"] for requirement in requirements):
            raise ValueError("v2 task needs a critical delivery requirement")
        facts = policy.get("owner_facts", [])
        if not isinstance(facts, list) or len(facts) > 32:
            raise ValueError("owner facts exceed limit")
        fact_ids = set()
        clarification_ids = {
            requirement["id"]
            for requirement in requirements
            if requirement.get("kind") == "clarification"
        }
        public_brief = (root / "TASK.md").read_text().casefold()
        for fact in facts:
            identity, matchers = fact.get("id", ""), fact.get("matchers")
            if (
                not IDENTIFIER.fullmatch(identity)
                or identity in fact_ids
                or not isinstance(fact.get("answer"), str)
                or not 1 <= len(fact["answer"].encode()) <= 2048
                or type(fact.get("required")) is not bool
                or not isinstance(matchers, list)
                or not 1 <= len(matchers) <= 8
                or any(
                    not isinstance(terms, list)
                    or not 1 <= len(terms) <= 8
                    or any(
                        not isinstance(term, str)
                        or not re.fullmatch(r"[a-z0-9_-]{1,48}", term)
                        for term in terms
                    )
                    for terms in matchers
                )
            ):
                raise ValueError("invalid authorized owner fact")
            fact_ids.add(identity)
            if fact["required"] and (
                fact.get("requirement_id") not in clarification_ids
                or fact["requirement_id"] not in public_brief
            ):
                raise ValueError(
                    "required questioning must be an explicit public clarification requirement"
                )
        milestones = policy.get("milestones", [])
        changes = policy.get("changes", [])
        if (
            not isinstance(milestones, list)
            or not isinstance(changes, list)
            or len(milestones) > 4
            or len(changes) > 4
        ):
            raise ValueError("bounded observable milestones required")
        milestone_ids = set()
        for milestone in milestones:
            identity = milestone.get("id", "")
            if (
                not IDENTIFIER.fullmatch(identity)
                or identity in milestone_ids
                or not isinstance(milestone.get("cases"), list)
                or not milestone["cases"]
                or not set(milestone["cases"]) <= case_ids
            ):
                raise ValueError("invalid observable milestone predicate")
            milestone_ids.add(identity)
        seen = set()
        for change in changes:
            if change.get("after") not in milestone_ids or change["after"] in seen:
                raise ValueError("change must follow one unique observable milestone")
            brief = relative_path(root, change.get("brief"))
            if (
                not brief.is_relative_to(root / "private")
                or not brief.is_file()
                or brief.stat().st_size > 16384
            ):
                raise ValueError("future change brief must be a bounded private asset")
            brief.read_bytes().decode("utf-8")
            seen.add(change["after"])
        if manifest["track"] == "B" and (not milestones or not changes):
            raise ValueError("evolving task requires observable change delivery")
        if manifest["track"] == "A" and (milestones or changes):
            raise ValueError("single-increment task cannot conceal change events")
        return cls(tuple(requirements), tuple(facts), tuple(milestones), tuple(changes))

    def acceptance(self, observed, *, asked_facts=None, reached_milestones=None):
        by_case = {}
        for check in observed["checks"]:
            if type(check.get("passed")) is not bool:
                raise ValueError("invalid evaluator evidence; acceptance is unknown")
            by_case.setdefault(check["case"], []).append(check["passed"])
        coverage = {}
        for requirement in self.requirements:
            states = [
                all(by_case[case]) if case in by_case else None
                for case in requirement["cases"]
            ]
            coverage[requirement["id"]] = (
                False if False in states else None if None in states else True
            )
        missing_facts = [
            fact["id"]
            for fact in self.owner_facts
            if fact["required"] and fact["id"] not in (asked_facts or ())
        ]
        for fact in self.owner_facts:
            if fact["required"] and fact["id"] in missing_facts:
                identity = fact["requirement_id"]
                if asked_facts is not None:
                    coverage[identity] = False
                elif coverage[identity] is not False:
                    coverage[identity] = None
        missing_changes = [
            change["after"]
            for change in self.changes
            if change["after"] not in (reached_milestones or ())
        ]
        critical = [
            coverage[requirement["id"]]
            for requirement in self.requirements
            if requirement["critical"]
        ]
        known_failure = (
            False in critical
            or (missing_facts and asked_facts is not None)
            or (missing_changes and reached_milestones is not None)
        )
        unknown = (
            None in critical
            or (missing_facts and asked_facts is None)
            or (missing_changes and reached_milestones is None)
        )
        return {
            "requirement_coverage": coverage,
            "missing_owner_facts": missing_facts,
            "missing_change_milestones": missing_changes,
            "intent_success": False if known_failure else None if unknown else True,
        }


class AuthorizedOwner:
    """Answer only predeclared facts; matching never sees the private grader."""

    def __init__(self, facts, journal, *, exchanges=6, unspecified="Not specified."):
        self.facts, self.journal, self.limit = facts, journal, exchanges
        self.unspecified = unspecified
        self.exchanges = self.individual_questions = self.refused_batches = 0
        self.answer_bytes = 0
        self.asked = set()

    def ask(self, params):
        questions = params.get("questions")
        if (
            not isinstance(questions, list)
            or not 1 <= len(questions) <= 4
            or len(json.dumps(params).encode()) > 16384
            or any(
                not isinstance(question.get("id"), str)
                or not isinstance(question.get("question"), str)
                for question in questions
            )
            or len({question["id"] for question in questions}) != len(questions)
        ):
            raise ValueError("invalid bounded owner question batch")
        self.individual_questions += len(questions)
        if self.exchanges >= self.limit:
            self.refused_batches += 1
            text = "Owner interaction allowance exhausted."
            volume = len(text.encode()) * len(questions)
            self.answer_bytes += volume
            self.journal.event(
                "owner_batch_refused",
                refused_batches=self.refused_batches,
                questions=len(questions),
                answer_bytes=volume,
            )
            return {
                "answers": {
                    question["id"]: {"answers": [text]} for question in questions
                }
            }
        self.exchanges += 1
        answers, mappings = {}, []
        for question in questions:
            words = set(re.findall(r"[\w-]+", question["question"].casefold()))
            matches = [
                fact
                for fact in self.facts
                if any(set(terms) <= words for terms in fact["matchers"])
            ]
            fact = matches[0] if len(matches) == 1 else None
            text = fact["answer"] if fact else self.unspecified
            self.answer_bytes += len(text.encode())
            if fact:
                self.asked.add(fact["id"])
            answers[question["id"]] = {"answers": [text]}
            mappings.append(
                {
                    "question": question["question"],
                    "fact_id": fact["id"] if fact else None,
                    "answer": text,
                }
            )
        self.journal.event("owner_exchange", exchange=self.exchanges, mappings=mappings)
        return {"answers": answers}

    def snapshot(self):
        return {
            "exchanges": self.exchanges,
            "individual_questions": self.individual_questions,
            "answer_bytes": self.answer_bytes,
            "refused_batches": self.refused_batches,
            "asked_facts": sorted(self.asked),
        }
