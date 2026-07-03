"""Rotas do módulo Pré-planejamento: estudos/cenários e a grade de ciclos
(serviços × pavimentos) de cada um. Autenticado por `get_current_user` (dono
do projeto) — não tem conceito de master, é dado de trabalho do dono, não
gestão de conta. RLS não protege o caminho do backend (DATABASE_URL direto),
então a checagem de "o projeto é seu" é feita explicitamente aqui, mesmo
padrão usado em domain/snapshots/process_import.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.dependencies import get_current_user, get_db
from app.domain.pre_planejamento import repository
from app.domain.pre_planejamento.repository import CycleInput, FloorInput, HolidayInput, ServiceInput
from app.schemas import (
    CreateStudyRequest,
    CycleOut,
    FloorOut,
    HolidayOut,
    SaveCyclesRequest,
    ServiceOut,
    StudyDetailOut,
    StudyOut,
    UpdateStudyRequest,
)

router = APIRouter()


async def _ensure_project_access(
    conn: asyncpg.connection.Connection, project_id: UUID, owner_id: UUID
) -> None:
    project_owner_id = await repository.get_project_owner_id(conn, project_id)
    if project_owner_id is None or project_owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")


async def _get_owned_study(
    conn: asyncpg.connection.Connection, project_id: UUID, study_id: UUID, owner_id: UUID
) -> asyncpg.Record:
    await _ensure_project_access(conn, project_id, owner_id)
    study = await repository.get_study(conn, study_id)
    if study is None or study["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")
    return study


@router.get("/pre-planejamento/{project_id}/estudos")
async def get_estudos(
    project_id: UUID,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> list[StudyOut]:
    await _ensure_project_access(conn, project_id, owner_id)
    rows = await repository.list_studies(conn, project_id)
    return [StudyOut(**dict(row)) for row in rows]


@router.post("/pre-planejamento/{project_id}/estudos", status_code=201)
async def post_estudo(
    project_id: UUID,
    body: CreateStudyRequest,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> StudyOut:
    await _ensure_project_access(conn, project_id, owner_id)
    study_id = await repository.create_study(conn, project_id, body.name, body.start_date)
    study = await repository.get_study(conn, study_id)
    return StudyOut(**dict(study))


@router.get("/pre-planejamento/{project_id}/estudos/{estudo_id}")
async def get_estudo(
    project_id: UUID,
    estudo_id: UUID,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> StudyDetailOut:
    study = await _get_owned_study(conn, project_id, estudo_id, owner_id)
    services = await repository.get_services(conn, estudo_id)
    floors = await repository.get_floors(conn, estudo_id)
    cycles = await repository.get_cycles(conn, estudo_id)
    holidays = await repository.get_holidays(conn, estudo_id)
    return StudyDetailOut(
        **dict(study),
        services=[ServiceOut(**dict(r)) for r in services],
        floors=[FloorOut(**dict(r)) for r in floors],
        cycles=[CycleOut(**dict(r)) for r in cycles],
        holidays=[HolidayOut(**dict(r)) for r in holidays],
    )


@router.put("/pre-planejamento/{project_id}/estudos/{estudo_id}")
async def put_estudo(
    project_id: UUID,
    estudo_id: UUID,
    body: UpdateStudyRequest,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> StudyDetailOut:
    await _get_owned_study(conn, project_id, estudo_id, owner_id)
    await repository.update_study(
        conn, estudo_id, body.name, body.start_date,
        [HolidayInput(date=h.date, description=h.description, is_national=h.is_national) for h in body.holidays],
    )
    return await get_estudo(project_id, estudo_id, owner_id, conn)


@router.delete("/pre-planejamento/{project_id}/estudos/{estudo_id}", status_code=204)
async def delete_estudo(
    project_id: UUID,
    estudo_id: UUID,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> Response:
    await _get_owned_study(conn, project_id, estudo_id, owner_id)
    await repository.delete_study(conn, estudo_id)
    return Response(status_code=204)


@router.put("/pre-planejamento/{project_id}/estudos/{estudo_id}/ciclos")
async def put_ciclos(
    project_id: UUID,
    estudo_id: UUID,
    body: SaveCyclesRequest,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> StudyDetailOut:
    await _get_owned_study(conn, project_id, estudo_id, owner_id)
    await repository.replace_cycles(
        conn, estudo_id,
        [ServiceInput(name=s.name, color=s.color, order_index=s.order_index, lag_days=s.lag_days) for s in body.services],
        [FloorInput(group_name=f.group_name, floor_name=f.floor_name, order_index=f.order_index) for f in body.floors],
        [CycleInput(service_index=c.service_index, floor_index=c.floor_index, duration_days=c.duration_days) for c in body.cycles],
    )
    return await get_estudo(project_id, estudo_id, owner_id, conn)
