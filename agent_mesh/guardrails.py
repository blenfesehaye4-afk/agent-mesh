"""PII identification & redaction and prompt injection heuristics."""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class GuardrailResult:
    sanitized_text: str
    violations: List[str]
    is_blocked: bool = False
    block_reason: str = ""


class GuardrailEngine:
    """Enterprise safety and privacy filter for LLM prompts."""

    PII_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
        ("API_KEY", re.compile(r"\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})\b"), "[REDACTED_API_KEY]"),
        ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
        ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[REDACTED_CREDIT_CARD]"),
        ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
    ]

    INJECTION_SIGNATURES = [
        "ignore previous instructions",
        "disregard all previous",
        "you are now dan",
        "bypass all guardrails",
        "system prompt override",
        "reveal your secret prompt",
    ]

    @classmethod
    def sanitize(cls, text: str) -> GuardrailResult:
        """Inspect text for prompt injections and mask any sensitive PII."""
        lower_text = text.lower()

        # 1. Prompt Injection detection
        for sig in cls.INJECTION_SIGNATURES:
            if sig in lower_text:
                return GuardrailResult(
                    sanitized_text=text,
                    violations=["PROMPT_INJECTION"],
                    is_blocked=True,
                    block_reason=f"Detected prompt injection pattern: '{sig}'",
                )

        # 2. PII Sanitization
        sanitized = text
        violations = []

        for pii_name, pattern, mask in cls.PII_PATTERNS:
            matches = pattern.findall(sanitized)
            if matches:
                violations.append(pii_name)
                sanitized = pattern.sub(mask, sanitized)

        return GuardrailResult(sanitized_text=sanitized, violations=violations, is_blocked=False)
