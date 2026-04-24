from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WikiSection(BaseModel):
    name: str
    managed_by: Literal["auto", "human"]
    content: str = ""


class WikiPage(BaseModel):
    page_type: str
    entity_id: str
    canonical_name: str
    path: str
    sections: dict[str, WikiSection] = Field(default_factory=dict)
    last_auto_updated: datetime | None = None
    last_human_edited: datetime | None = None
