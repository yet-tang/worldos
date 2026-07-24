from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


class Intent(BaseModel):
    """A requested world action. Intents describe desire, never authoritative state change."""

    tick: int
    intent_type: str
    actor_id: str
    target_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def deterministic_id(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"int_{hashlib.sha256(canonical.encode()).hexdigest()[:24]}"


class ValidationIssue(BaseModel):
    code: str
    message: str
    subject_id: str | None = None


class ValidationResult(BaseModel):
    accepted: bool
    issues: tuple[ValidationIssue, ...] = ()

    @classmethod
    def accept(cls) -> "ValidationResult":
        return cls(accepted=True)

    @classmethod
    def reject(cls, *issues: ValidationIssue) -> "ValidationResult":
        return cls(accepted=False, issues=issues)
