"""Schemas de request/response de /api/v1/pre-planejamento."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class StudyOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    start_date: date
    created_at: datetime


class ServiceOut(BaseModel):
    id: UUID
    name: str
    color: str
    order_index: int
    lag_days: int


class FloorOut(BaseModel):
    id: UUID
    group_name: str
    floor_name: str
    order_index: int


class CycleOut(BaseModel):
    id: UUID
    service_id: UUID
    floor_id: UUID
    duration_days: int


class HolidayOut(BaseModel):
    id: UUID
    date: date
    description: str
    is_national: bool


class StudyDetailOut(StudyOut):
    services: list[ServiceOut]
    floors: list[FloorOut]
    cycles: list[CycleOut]
    holidays: list[HolidayOut]


class CreateStudyRequest(BaseModel):
    name: str
    start_date: date


class HolidayIn(BaseModel):
    date: date
    description: str
    is_national: bool = False


class UpdateStudyRequest(BaseModel):
    name: str
    start_date: date
    holidays: list[HolidayIn]


class ServiceIn(BaseModel):
    name: str
    color: str
    order_index: int
    lag_days: int = 0


class FloorIn(BaseModel):
    group_name: str
    floor_name: str
    order_index: int


class CycleIn(BaseModel):
    service_index: int
    floor_index: int
    duration_days: int


class SaveCyclesRequest(BaseModel):
    services: list[ServiceIn]
    floors: list[FloorIn]
    cycles: list[CycleIn]
