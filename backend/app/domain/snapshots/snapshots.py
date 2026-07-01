"""Decide o tipo de importação (inicial / atualização mensal / mudança
estrutural) e orquestra a gravação correspondente, usando os mapeamentos
puros de domain/import_mpp e os bulk inserts de infra/db/bulk.

process_import() é o único ponto de entrada — recebe uma conexão já aberta
(asyncpg) e não gerencia transação: quem chama decide o escopo do
`async with conn.transaction():`.

Mudança estrutural (tasks/dependencies novas ou removidas) nunca aplica nada
em tasks/dependencies/snapshots — só grava um registro em pending_imports
para confirmação posterior (item futuro, ver plano do item 6). Em especial,
task removida NÃO é apagada quando essa confirmação for implementada — vai
virar soft-delete (decisão do usuário em 2026-07-01, para preservar
task_progress histórico) — mas isso ainda não existe nesta etapa.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.domain.import_mpp import (
    get_project_guid,
    get_project_name,
    map_dependencies,
    map_task_progress,
    map_task_progress_by_ms_uid,
    map_tasks,
)
from app.infra.db.bulk import (
    DEPENDENCY_COLUMNS,
    TASK_COLUMNS,
    bulk_insert_dependencies,
    bulk_insert_task_progress,
    bulk_insert_tasks,
    fetch_task_id_map,
)

_PROGRESS_BY_MS_UID_COLUMNS = (
    "ms_uid", "planned_start", "planned_finish", "forecast_start",
    "forecast_finish", "actual_start", "actual_finish", "percent_complete",
)


class ImportType(str, Enum):
    INITIAL = "initial"
    MONTHLY_UPDATE = "monthly_update"
    STRUCTURAL_CHANGE = "structural_change"


@dataclass
class ImportResult:
    import_type: ImportType
    project_id: UUID
    snapshot_id: UUID | None        # None quando STRUCTURAL_CHANGE
    pending_import_id: UUID | None  # só quando STRUCTURAL_CHANGE
    diff_summary: dict | None       # só quando STRUCTURAL_CHANGE


async def process_import(
    conn: asyncpg.connection.Connection,
    owner_id: UUID,
    project: Any,
    fallback_name: str,
    reference_month: date,
    file_url: str | None = None,
) -> ImportResult:
    guid = get_project_guid(project)
    existing_project_id = await _find_project_by_guid(conn, owner_id, guid) if guid else None
    project_id = existing_project_id or uuid4()

    mapped_tasks = map_tasks(project, project_id)
    mapped_deps = map_dependencies(project, project_id)

    if existing_project_id is None:
        project_name = get_project_name(project, fallback_name)
        snapshot_id = await _apply_initial_import(
            conn, owner_id, project_id, project_name, guid,
            mapped_tasks, mapped_deps, project, reference_month, file_url,
        )
        return ImportResult(ImportType.INITIAL, project_id, snapshot_id, None, None)

    existing_task_uids, existing_dep_keys = await _existing_structure(conn, project_id)
    new_task_uids = {row[1] for row in mapped_tasks}
    new_dep_keys = {(row[1], row[2], row[3]) for row in mapped_deps}

    if new_task_uids == existing_task_uids and new_dep_keys == existing_dep_keys:
        snapshot_id = await _apply_monthly_update(conn, project_id, project, reference_month, file_url)
        return ImportResult(ImportType.MONTHLY_UPDATE, project_id, snapshot_id, None, None)

    diff_summary = _diff_summary(new_task_uids, existing_task_uids, new_dep_keys, existing_dep_keys)
    pending_import_id = await _stage_structural_change(
        conn, owner_id, project_id, diff_summary, mapped_tasks, mapped_deps, project, file_url,
    )
    return ImportResult(ImportType.STRUCTURAL_CHANGE, project_id, None, pending_import_id, diff_summary)


async def _find_project_by_guid(
    conn: asyncpg.connection.Connection, owner_id: UUID, guid: str
) -> UUID | None:
    return await conn.fetchval(
        "select id from projects where owner_id = $1 and ms_project_guid = $2",
        owner_id, guid,
    )


async def _existing_structure(
    conn: asyncpg.connection.Connection, project_id: UUID
) -> tuple[set[int], set[tuple[int, int, str]]]:
    task_rows = await conn.fetch("select ms_uid from tasks where project_id = $1", project_id)
    dep_rows = await conn.fetch(
        "select predecessor_uid, successor_uid, type from dependencies where project_id = $1",
        project_id,
    )
    task_uids = {row["ms_uid"] for row in task_rows}
    dep_keys = {(row["predecessor_uid"], row["successor_uid"], row["type"]) for row in dep_rows}
    return task_uids, dep_keys


def _diff_summary(
    new_task_uids: set[int], existing_task_uids: set[int],
    new_dep_keys: set[tuple[int, int, str]], existing_dep_keys: set[tuple[int, int, str]],
) -> dict:
    return {
        "tasks_added": len(new_task_uids - existing_task_uids),
        "tasks_removed": len(existing_task_uids - new_task_uids),
        "dependencies_added": len(new_dep_keys - existing_dep_keys),
        "dependencies_removed": len(existing_dep_keys - new_dep_keys),
    }


async def _apply_initial_import(
    conn: asyncpg.connection.Connection,
    owner_id: UUID,
    project_id: UUID,
    project_name: str,
    project_guid: str | None,
    mapped_tasks: list[tuple],
    mapped_deps: list[tuple],
    project: Any,
    reference_month: date,
    file_url: str | None,
) -> UUID:
    await conn.execute(
        "insert into projects (id, name, owner_id, ms_project_guid) values ($1, $2, $3, $4)",
        project_id, project_name, owner_id, project_guid,
    )
    await bulk_insert_tasks(conn, mapped_tasks)
    await bulk_insert_dependencies(conn, mapped_deps)

    snapshot_id = await conn.fetchval(
        "insert into snapshots (project_id, reference_month, is_baseline, file_url) "
        "values ($1, $2, true, $3) returning id",
        project_id, reference_month, file_url,
    )
    task_id_map = await fetch_task_id_map(conn, project_id)
    progress = map_task_progress(project, snapshot_id, task_id_map)
    await bulk_insert_task_progress(conn, progress)
    return snapshot_id


async def _apply_monthly_update(
    conn: asyncpg.connection.Connection,
    project_id: UUID,
    project: Any,
    reference_month: date,
    file_url: str | None,
) -> UUID:
    snapshot_id = await conn.fetchval(
        "insert into snapshots (project_id, reference_month, is_baseline, file_url) "
        "values ($1, $2, false, $3) returning id",
        project_id, reference_month, file_url,
    )
    task_id_map = await fetch_task_id_map(conn, project_id)
    progress = map_task_progress(project, snapshot_id, task_id_map)
    await bulk_insert_task_progress(conn, progress)
    return snapshot_id


def _json_default(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Tipo não serializável em pending_imports.payload: {type(value)}")


async def _stage_structural_change(
    conn: asyncpg.connection.Connection,
    owner_id: UUID,
    project_id: UUID,
    diff_summary: dict,
    mapped_tasks: list[tuple],
    mapped_deps: list[tuple],
    project: Any,
    file_url: str | None,
) -> UUID:
    payload = {
        "tasks": [dict(zip(TASK_COLUMNS[1:], row[1:])) for row in mapped_tasks],
        "dependencies": [dict(zip(DEPENDENCY_COLUMNS[1:], row[1:])) for row in mapped_deps],
        "task_progress": [
            dict(zip(_PROGRESS_BY_MS_UID_COLUMNS, row))
            for row in map_task_progress_by_ms_uid(project)
        ],
    }
    return await conn.fetchval(
        "insert into pending_imports "
        "(project_id, owner_id, file_url, diff_summary, payload, status) "
        "values ($1, $2, $3, $4::jsonb, $5::jsonb, 'pending') returning id",
        project_id, owner_id, file_url,
        json.dumps(diff_summary), json.dumps(payload, default=_json_default),
    )
