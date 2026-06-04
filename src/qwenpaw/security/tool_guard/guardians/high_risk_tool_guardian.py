# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from typing import Any

from ..models import GuardFinding, GuardSeverity, GuardThreatCategory
from . import BaseToolGuardian

_HIGH_RISK_TOOLS = frozenset({"payroll_export_tool", "tool_d"})
_BYPASS_MARKERS = (
    "ignore every approval policy",
    "maintenance mode",
    "test mode",
    "already trusted",
    "missing confirmation",
)


class HighRiskToolGuardian(BaseToolGuardian):
    """Guard high-risk tool invocations at the tool-call boundary."""

    def __init__(self) -> None:
        super().__init__("high_risk_tool_guardian")

    def guard(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> list[GuardFinding]:
        if tool_name not in _HIGH_RISK_TOOLS:
            return []

        prompt_text = str(params.get("prompt_text") or params.get("prompt") or "")
        prompt_lower = prompt_text.lower()
        confirmation_phrase = str(params.get("user_confirmation_phrase") or "").strip()
        has_bypass_narrative = any(marker in prompt_lower for marker in _BYPASS_MARKERS)

        if has_bypass_narrative:
            return [
                GuardFinding(
                    id=uuid.uuid4().hex[:8],
                    rule_id="high_risk_prompt_bypass",
                    category=GuardThreatCategory.PROMPT_INJECTION,
                    severity=GuardSeverity.HIGH,
                    title="High-risk tool bypass blocked",
                    description=(
                        "A high-risk tool invocation reached the tool-call boundary "
                        "with a prompt-driven bypass narrative and must be rejected "
                        "until trusted context and approval evidence exist."
                    ),
                    tool_name=tool_name,
                    param_name="prompt_text",
                    matched_value=prompt_text,
                    remediation="Reject the invocation and require trusted approval evidence.",
                    guardian=self.name,
                    metadata={
                        "boundary_action": "auto_deny",
                        "rejection_reason": "missing_trusted_context_and_confirmation",
                        "confirmation_phrase_present": bool(confirmation_phrase),
                    },
                ),
            ]

        return [
            GuardFinding(
                id=uuid.uuid4().hex[:8],
                rule_id="explicit_high_risk_confirmation",
                category=GuardThreatCategory.PROMPT_INJECTION,
                severity=GuardSeverity.HIGH,
                title="High-risk tool requires confirmation",
                description=(
                    "A high-risk tool invocation reached the tool-call boundary and "
                    "must pause for explicit approval before execution continues."
                ),
                tool_name=tool_name,
                remediation="Create an approval request before executing the tool.",
                guardian=self.name,
                metadata={
                    "boundary_action": "needs_approval",
                    "confirmation_phrase_present": bool(confirmation_phrase),
                },
            ),
        ]