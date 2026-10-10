"""Validated wire contracts for inbound monitoring events."""
from __future__ import annotations

import secrets
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageType = Literal["CRITICAL", "WARNING", "ACKNOWLEDGEMENT", "INFO", "RECOVERY"]


class AlertPayload(BaseModel):
    message_type: MessageType
    # The REST Endpoint documentation permits an omitted entity_id; generate one
    # for that single event. Producers should still send a stable ID for lifecycle
    # correlation across trigger/acknowledgement/recovery messages.
    entity_id: str = Field(default_factory=lambda: secrets.token_urlsafe(18), min_length=1, max_length=256)
    entity_display_name: str | None = Field(default=None, max_length=256)
    state_message: str = Field(default="", max_length=10000)
    timestamp: int | float | None = None
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    @field_validator("entity_id")
    @classmethod
    def entity_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("entity_id must not be blank")
        return value

    @field_validator("entity_display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value
