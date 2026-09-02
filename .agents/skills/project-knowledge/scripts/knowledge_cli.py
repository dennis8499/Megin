#!/usr/bin/env python3
"""Public command-line seam for project knowledge operations."""

from __future__ import annotations

import argparse
import json
import os
import sys

from knowledge_query import KnowledgeError, query_repository

BOOTSTRAP_SENTINEL = "BOOTSTRAP_SENTINEL"
BOOTSTRAP_EXIT = 78


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    query = subcommands.add_parser("query")
    query.add_argument("--repo", required=True)
    query.add_argument(
        "--stage",
        required=True,
        choices=["requirements", "planning", "implementation", "bug", "ad-hoc"],
    )
    query.add_argument("--query", required=True)

    bootstrap = subcommands.add_parser("bootstrap")
    bootstrap.add_argument("--repo", required=True)
    bootstrap.add_argument("--approval-actor", required=True)
    bootstrap.add_argument("--approval-evidence", required=True)
    lint = subcommands.add_parser("lint")
    lint.add_argument("--repo", required=True)
    lint.add_argument("--approval-actor")
    lint.add_argument("--approval-evidence")
    recover = subcommands.add_parser("recover")
    recover.add_argument("--repo", required=True)
    candidate = subcommands.add_parser("candidate")
    candidate.add_argument("--repo", required=True)
    candidate.add_argument("--draft", required=True)
    candidate.add_argument("--approval-actor", required=True)
    candidate.add_argument("--approval-evidence", required=True)
    candidate.add_argument("--known-secret-env", action="append", default=[])
    apply = subcommands.add_parser("apply")
    apply.add_argument("--repo", required=True)
    apply.add_argument("--candidate-ref", required=True)
    apply.add_argument("--approval-actor", required=True)
    apply.add_argument("--approval-evidence", required=True)
    apply.add_argument("--known-secret-env", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "query":
            result = query_repository(
                arguments.repo,
                stage=arguments.stage,
                query=arguments.query,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "bootstrap":
            from knowledge_governance import bootstrap_repository

            result = bootstrap_repository(
                arguments.repo,
                approval_actor=arguments.approval_actor,
                approval_evidence=arguments.approval_evidence,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "lint":
            from knowledge_governance import lint_repository

            if bool(arguments.approval_actor) != bool(arguments.approval_evidence):
                raise KnowledgeError(
                    "APPROVAL_BINDING_INVALID",
                    "lint repair sealing requires both approval actor and evidence token",
                    exit_code=2,
                )
            result = lint_repository(
                arguments.repo,
                repair_approval_actor=arguments.approval_actor,
                repair_approval_evidence=arguments.approval_evidence,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "candidate":
            from knowledge_promotion import seal_candidate_file

            known_secrets = tuple(
                os.environ[name]
                for name in arguments.known_secret_env
                if name in os.environ and os.environ[name]
            )
            result = seal_candidate_file(
                arguments.repo,
                draft_path=arguments.draft,
                approval_actor=arguments.approval_actor,
                approval_evidence=arguments.approval_evidence,
                known_secret_values=known_secrets,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "apply":
            from knowledge_promotion import apply_candidate

            known_secrets = tuple(
                os.environ[name]
                for name in arguments.known_secret_env
                if name in os.environ and os.environ[name]
            )
            result = apply_candidate(
                arguments.repo,
                candidate_ref=arguments.candidate_ref,
                approval_actor=arguments.approval_actor,
                approval_evidence=arguments.approval_evidence,
                known_secret_values=known_secrets,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "recover":
            from knowledge_promotion import recover_repository

            result = recover_repository(arguments.repo)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        print(BOOTSTRAP_SENTINEL)
        return BOOTSTRAP_EXIT
    except KnowledgeError as exc:
        error = {
            "schema": "knowledge-error/v1",
            "code": exc.code,
            "message": str(exc),
            "evidence_refs": exc.evidence_refs,
            "recoverable": exc.recoverable,
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


