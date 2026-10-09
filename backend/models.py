"""Extraction schema and the intent vocabulary shared by the backend."""

from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator


Intent = Literal[
    "price_comparison", "alternative_search", "side_effects",
    "interaction_check", "usage_information", "availability",
    "prescription_status", "diagnosis_request", "prescribing_request",
    "general_health", "other",
]

BLOCKED_INTENTS = {
    "prescribing_request": "I cannot prescribe medicines. Please consult your doctor.",
    "diagnosis_request": "I cannot diagnose medical conditions. Please consult your doctor.",
    "interaction_check": (
        "Please consult your doctor or pharmacist before combining medicines."
    ),
    "usage_information" : "I cannot prescribe the usage.Please consult a doctor. ",
}
# Every declared non-blocked intent is accepted for downstream handling.
SUPPORTED_INTENTS = set(get_args(Intent)) - set(BLOCKED_INTENTS)


class Medicine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strength: str | None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicines: list[Medicine]
    intents: list[Intent] = Field(min_length=1)
    needs_clarification: bool
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_clarification(self) -> Self:
        # Blocked requests never depend on clarification; route them immediately.
        if set(self.intents).intersection(BLOCKED_INTENTS):
            return self
        if self.needs_clarification:
            if not self.clarification_question or not self.clarification_question.strip():
                raise ValueError("Clarification requires a non-empty question.")
        elif self.clarification_question is not None:
            raise ValueError("clarification_question must be null when clarification is unnecessary.")
        return self
