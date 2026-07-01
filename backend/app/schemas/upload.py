"""Schema de resposta de POST /upload."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    import_type: Literal["initial", "monthly_update", "structural_change"]
    project_id: UUID
    snapshot_id: UUID | None
    pending_import_id: UUID | None
    diff_summary: dict | None
