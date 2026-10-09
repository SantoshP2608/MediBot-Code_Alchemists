"""Extraction schema and the intent vocabulary shared by the backend."""

from backend.config.settings import CONSTANTS

from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator


Intent = Literal[*CONSTANTS["intents"]]

BLOCKED_INTENTS = CONSTANTS["blocked_intents"]
# Every declared non-blocked intent is accepted for downstream handling.
SUPPORTED_INTENTS = set(get_args(Intent)) - set(BLOCKED_INTENTS)


class Medicine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strength: str | None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicines: list[Medicine]
    intents: list[Intent] = Field(min_length=CONSTANTS["routing"]["minimum_intents"])
    needs_clarification: bool
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_clarification(self) -> Self:
        # Blocked requests never depend on clarification; route them immediately.
        if set(self.intents).intersection(BLOCKED_INTENTS):
            return self
        if self.needs_clarification:
            if not self.clarification_question or not self.clarification_question.strip():
                raise ValueError(CONSTANTS["messages"]["clarification_required"])
        elif self.clarification_question is not None:
            raise ValueError(CONSTANTS["messages"]["unexpected_clarification_question"])
        return self
