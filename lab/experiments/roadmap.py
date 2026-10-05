"""Export reviewed idea-to-increment proposals as normal Codex kickoff prompts."""

import argparse
import json
from pathlib import Path

from workflows.roadmap import propose, export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--intent", type=Path, required=True, help="Original free-form user intent"
    )
    parser.add_argument(
        "--proposal",
        type=Path,
        required=True,
        help="Planner JSON: requirements, mapped increments, questions and decision context; see workflows/our_v0.py PLAN_SCHEMA",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory for portable kickoff prompts",
    )
    parser.add_argument(
        "--previous", type=Path, help="Prior roadmap.json for a revision"
    )
    parser.add_argument(
        "--discovery",
        type=Path,
        help="Concrete discovery or explicit follow-up request",
    )
    parser.add_argument(
        "--completed",
        action="append",
        default=[],
        help="Completed increment ID retained by a revision",
    )
    parser.add_argument(
        "--owner-followup",
        type=Path,
        help="Explicit user-authored addition; never inferred from agent discovery",
    )
    args = parser.parse_args()
    for path in (
        args.intent,
        args.proposal,
        args.previous,
        args.discovery,
        args.owner_followup,
    ):
        if path is not None and path.stat().st_size > 65536:
            parser.error("roadmap input exceeds64KiB")
    result = propose(
        args.intent.read_text(encoding="utf-8"),
        args.proposal.read_text(encoding="utf-8"),
        previous=json.loads(args.previous.read_text(encoding="utf-8"))
        if args.previous
        else None,
        discovery=args.discovery.read_text(encoding="utf-8")
        if args.discovery
        else None,
        completed=args.completed,
        owner_followup=args.owner_followup.read_text(encoding="utf-8")
        if args.owner_followup
        else None,
    )
    print(export(result, args.output))


if __name__ == "__main__":
    main()
