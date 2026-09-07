#!/usr/bin/env python3
"""Typed validation boundaries for delivery phase transitions.

The public facade owns locking and atomic persistence. These handlers own the
phase-specific input shape and next-state checks used by the record coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from _delivery_runtime import DeliveryError, PHASE_TRANSITIONS, STATUS_TRANSITIONS


def _provided(value: Any) -> bool:
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    return value is not None


@dataclass(frozen=True)
class OptionalBinding:
    values: tuple[Any, ...]

    @property
    def supplied(self) -> bool:
        return any(_provided(value) for value in self.values)

    @property
    def complete(self) -> bool:
        return all(_provided(value) for value in self.values)


@dataclass(frozen=True)
class TransitionRequest:
    current_phase: str
    current_status: str
    phase: str
    status: str
    requirements: OptionalBinding
    plan: OptionalBinding
    implementation: OptionalBinding
    knowledge_review: OptionalBinding
    promotion: OptionalBinding
    bug_verification: OptionalBinding = OptionalBinding(())


@dataclass(frozen=True)
class TransitionContext:
    """Frozen coordination boundary for phase-owned validation and binding."""

    request: TransitionRequest
    record: dict[str, Any]
    values: Mapping[str, Any]
    state: MutableMapping[str, Any]
    operations: Mapping[str, Callable[["TransitionContext"], None]]

    def run(self, operation: str) -> None:
        try:
            callback = self.operations[operation]
        except KeyError as exc:
            raise DeliveryError(
                f"transition operation is unavailable: {operation}",
                code="INVALID_RECORD",
            ) from exc
        callback(self)


class TransitionPhaseHandler:
    phase: str

    def __init__(self, phase: str) -> None:
        self.phase = phase

    @staticmethod
    def next_state(request: TransitionRequest) -> tuple[str, str]:
        return request.phase, request.status

    def bind(self, context: TransitionContext) -> None:
        context.run(self.phase)


class RequirementsTransitionHandler(TransitionPhaseHandler):
    def validate_artifact(self, request: TransitionRequest) -> None:
        if request.requirements.supplied and not request.requirements.complete:
            raise DeliveryError(
                "Ready requirements require path, hash, and approval evidence",
                code="INCOMPLETE_ARTIFACT_REF",
            )
        if request.requirements.supplied and (request.phase, request.status) != (
            "planning",
            "active",
        ):
            raise DeliveryError(
                "Ready requirements must atomically advance to planning/active",
                code="MISSING_GATE",
            )

    def require_advance(self, request: TransitionRequest) -> None:
        if (
            request.phase == "planning"
            and request.current_phase == "requirements"
            and not request.requirements.supplied
        ):
            raise DeliveryError(
                "planning requires a newly persisted Ready requirements revision",
                code="MISSING_GATE",
            )


class PlanningTransitionHandler(TransitionPhaseHandler):
    def validate_artifact(self, request: TransitionRequest) -> None:
        if request.plan.supplied and not request.plan.complete:
            raise DeliveryError(
                "Ready plan requires handoff, revision, payload hash, and approval evidence",
                code="INCOMPLETE_ARTIFACT_REF",
            )
        if request.plan.supplied and (request.phase, request.status) != (
            "implementation",
            "active",
        ):
            raise DeliveryError(
                "Ready plan must atomically advance to implementation/active",
                code="MISSING_GATE",
            )

    def require_advance(self, request: TransitionRequest) -> None:
        if (
            request.phase == "implementation"
            and request.current_phase == "planning"
            and not request.plan.supplied
        ):
            raise DeliveryError(
                "implementation requires the newly Ready plan and may not ask a third approval",
                code="MISSING_GATE",
            )


class ImplementationTransitionHandler(TransitionPhaseHandler):
    def validate_verification(self, request: TransitionRequest) -> None:
        if request.bug_verification.supplied and not request.bug_verification.complete:
            raise DeliveryError(
                "BUG verification requires path, hash, and result",
                code="INCOMPLETE_ARTIFACT_REF",
            )

    def validate_run(self, request: TransitionRequest) -> None:
        if request.implementation.supplied and not request.implementation.complete:
            raise DeliveryError(
                "implementation ref requires run ID, Ledger ref, and status",
                code="INCOMPLETE_ARTIFACT_REF",
            )
        if request.implementation.complete:
            implementation_status = request.implementation.values[2]
            if implementation_status not in {
                "Active",
                "Complete",
                "Awaiting upstream reapproval",
                "Blocked",
            }:
                raise DeliveryError(
                    "invalid implementation status",
                    code="INVALID_IMPLEMENTATION_REF",
                )


class KnowledgeTransitionHandler(TransitionPhaseHandler):
    def validate_review(self, request: TransitionRequest) -> None:
        if request.knowledge_review.supplied and not request.knowledge_review.complete:
            raise DeliveryError(
                "knowledge review requires Candidate, dual snapshots, product snapshot, and outcome",
                code="INCOMPLETE_KNOWLEDGE_REVIEW",
            )

    def validate_promotion(self, request: TransitionRequest) -> None:
        if request.promotion.supplied and not request.promotion.complete:
            raise DeliveryError(
                "knowledge promotion requires ID, receipt path/hash, and approval evidence",
                code="INCOMPLETE_KNOWLEDGE_PROMOTION",
            )

    def validate_context(self, context: TransitionContext) -> None:
        if context.request.knowledge_review.supplied and (
            context.values.get("knowledge_candidate_ref") is None
            or context.values.get("knowledge_candidate_payload_sha256") is None
        ):
            raise DeliveryError(
                "knowledge review requires Candidate, dual snapshots, product snapshot, and outcome",
                code="INCOMPLETE_KNOWLEDGE_REVIEW",
            )


PHASE_HANDLERS: dict[str, TransitionPhaseHandler] = {
    "requirements": RequirementsTransitionHandler("requirements"),
    "planning": PlanningTransitionHandler("planning"),
    "implementation": ImplementationTransitionHandler("implementation"),
    "knowledge": KnowledgeTransitionHandler("knowledge"),
}


def validate_transition_route(request: TransitionRequest) -> tuple[str, str]:
    if request.phase not in PHASE_TRANSITIONS.get(request.current_phase, set()):
        raise DeliveryError(
            f"illegal phase transition {request.current_phase} -> {request.phase}",
            code="ILLEGAL_TRANSITION",
        )
    if request.status not in STATUS_TRANSITIONS.get(request.current_status, set()):
        raise DeliveryError(
            f"illegal status transition {request.current_status} -> {request.status}",
            code="ILLEGAL_TRANSITION",
        )
    if (
        request.current_status == "blocked"
        and request.status == "active"
        and request.phase != request.current_phase
    ):
        raise DeliveryError(
            "blocked recovery must remain in the same phase",
            code="ILLEGAL_TRANSITION",
        )
    if request.status == "awaiting_user" and request.phase not in {
        "requirements",
        "planning",
        "knowledge",
    }:
        raise DeliveryError(
            "awaiting_user is only valid for requirements, planning, or knowledge",
            code="ILLEGAL_TRANSITION",
        )
    if (request.phase == "complete") != (request.status == "complete"):
        raise DeliveryError(
            "complete phase and status must be paired",
            code="ILLEGAL_TRANSITION",
        )
    return request.phase, request.status


def apply_transition_handlers(context: TransitionContext) -> None:
    """Apply phase validations and bindings in the compatibility-preserving order."""

    context.run("prepare")
    knowledge = PHASE_HANDLERS["knowledge"]
    knowledge.validate_review(context.request)
    knowledge.validate_context(context)
    knowledge.validate_promotion(context.request)
    context.run("bugs")

    requirements = PHASE_HANDLERS["requirements"]
    requirements.validate_artifact(context.request)
    requirements.bind(context)

    planning = PHASE_HANDLERS["planning"]
    planning.validate_artifact(context.request)
    planning.bind(context)

    implementation = PHASE_HANDLERS["implementation"]
    implementation.validate_verification(context.request)
    implementation.validate_run(context.request)
    implementation.bind(context)

    knowledge.bind(context)
    requirements.require_advance(context.request)
    planning.require_advance(context.request)
