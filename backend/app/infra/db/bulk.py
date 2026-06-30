"""Bulk insert via COPY (asyncpg) para tasks, dependencies e task_progress.

COPY é usado em vez de INSERT em lote porque cronogramas de obra reais têm
10-20 mil linhas (ver docs/referencia-projeto.md, seção 4 — "Bulk insert
obrigatório para projetos de 10-20 mil linhas"). O mapeamento de
org.mpxj.ProjectFile para as tuplas aceitas aqui é responsabilidade de
app/domain/import_mpp, não deste módulo.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

import asyncpg

TASK_COLUMNS = (
    "project_id", "ms_uid", "wbs", "name", "level", "type", "duration", "is_milestone",
)
DEPENDENCY_COLUMNS = (
    "project_id", "predecessor_uid", "successor_uid", "type", "lag_days",
)
TASK_PROGRESS_COLUMNS = (
    "snapshot_id", "task_id", "planned_start", "planned_finish",
    "forecast_start", "forecast_finish", "actual_start", "actual_finish",
    "percent_complete",
)


def _copy_row_count(status: str) -> int:
    """'COPY 1234' -> 1234. Formato de retorno documentado do asyncpg para COPY."""
    return int(status.rsplit(maxsplit=1)[-1])


async def bulk_insert_tasks(
    conn: asyncpg.connection.Connection, records: Sequence[tuple]
) -> int:
    """records na ordem de TASK_COLUMNS. Retorna o nº de linhas inseridas."""
    status = await conn.copy_records_to_table("tasks", records=records, columns=TASK_COLUMNS)
    return _copy_row_count(status)


async def bulk_insert_dependencies(
    conn: asyncpg.connection.Connection, records: Sequence[tuple]
) -> int:
    """records na ordem de DEPENDENCY_COLUMNS. Retorna o nº de linhas inseridas."""
    status = await conn.copy_records_to_table(
        "dependencies", records=records, columns=DEPENDENCY_COLUMNS
    )
    return _copy_row_count(status)


async def bulk_insert_task_progress(
    conn: asyncpg.connection.Connection, records: Sequence[tuple]
) -> int:
    """records na ordem de TASK_PROGRESS_COLUMNS. Retorna o nº de linhas inseridas."""
    status = await conn.copy_records_to_table(
        "task_progress", records=records, columns=TASK_PROGRESS_COLUMNS
    )
    return _copy_row_count(status)


async def fetch_task_id_map(
    conn: asyncpg.connection.Connection, project_id: UUID
) -> dict[int, UUID]:
    """Mapeia ms_uid -> id (uuid) das tasks de um projeto.

    COPY não retorna os ids gerados (diferente de INSERT...RETURNING), e
    task_progress.task_id referencia tasks.id — não ms_uid. Por isso, depois
    de bulk_insert_tasks, esse mapeamento precisa ser buscado antes de montar
    os registros de bulk_insert_task_progress.
    """
    rows = await conn.fetch(
        "select ms_uid, id from tasks where project_id = $1", project_id
    )
    return {row["ms_uid"]: row["id"] for row in rows}
