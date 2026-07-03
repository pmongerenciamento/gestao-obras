"""Schemas de request/response de /api/v1/users."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

MembershipStatus = Literal["pending", "active", "blocked"]


class ProjectMembershipOut(BaseModel):
    project_id: UUID
    project_name: str
    status: MembershipStatus


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    avatar_url: str | None
    created_at: datetime
    email_confirmed_at: datetime | None
    banned: bool
    memberships: list[ProjectMembershipOut]


class CreateUserRequest(BaseModel):
    email: str
    full_name: str
    project_ids: list[UUID]


class UserActionRequest(BaseModel):
    action: Literal["block", "unblock", "reset_password", "grant", "set_avatar"]
    project_id: UUID | None = None
    avatar_url: str | None = None
