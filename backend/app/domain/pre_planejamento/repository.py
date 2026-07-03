"""Acesso a dados do módulo Pré-planejamento via asyncpg.

replace_holidays e replace_wbs_overrides usam replace completo (delete +
reinsert) — a UI sempre manda o estado inteiro (calendário/predecessores),
não patches incrementais, e nada mais referencia o `id` de um feriado ou de
um override, então perder a identidade a cada save não tem custo.

replace_cycles é diferente: precisa preservar o UUID de serviço/pavimento/
ciclo que continuam existindo entre saves, porque sim_wbs_overrides (aba
Estrutura WBS) referencia sim_cycles.id — se cada save da grade recriasse
tudo do zero (delete-and-reinsert cego, como era antes), qualquer save em
"Serviços e lotes" apagaria os predecessores cadastrados na WBS via cascade,
mesmo sem o usuário ter mudado nada relevante. Por isso agora é um upsert
reconciliador (update o que já existe, insere o que é novo, apaga o que
sumiu do payload).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

import asyncpg

from .holidays import generate_national_holidays

_HOLIDAY_YEARS_WINDOW = 4


@dataclass
class ServiceInput:
    name: str
    color: str
    order_index: int
    lag_days: int
    id: UUID | None = None


@dataclass
class FloorInput:
    group_name: str
    floor_name: str
    order_index: int
    id: UUID | None = None


@dataclass
class CycleInput:
    service_index: int
    floor_index: int
    duration_days: int


@dataclass
class HolidayInput:
    date: date
    description: str
    is_national: bool


@dataclass
class WbsOverrideInput:
    cycle_id: UUID
    predecessor_ids: list[UUID]


async def get_project_owner_id(conn: asyncpg.connection.Connection, project_id: UUID) -> UUID | None:
    return await conn.fetchval("select owner_id from projects where id = $1", project_id)


async def list_studies(conn: asyncpg.connection.Connection, project_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select id, project_id, name, start_date, created_at from sim_studies "
        "where project_id = $1 order by created_at desc",
        project_id,
    )


async def get_study(conn: asyncpg.connection.Connection, study_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "select id, project_id, name, start_date, created_at from sim_studies where id = $1",
        study_id,
    )


async def get_services(conn: asyncpg.connection.Connection, study_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select id, name, color, order_index, lag_days from sim_services "
        "where study_id = $1 order by order_index",
        study_id,
    )


async def get_floors(conn: asyncpg.connection.Connection, study_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select id, group_name, floor_name, order_index from sim_floors "
        "where study_id = $1 order by order_index",
        study_id,
    )


async def get_cycles(conn: asyncpg.connection.Connection, study_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select id, service_id, floor_id, duration_days from sim_cycles where study_id = $1",
        study_id,
    )


async def get_holidays(conn: asyncpg.connection.Connection, study_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select id, date, description, is_national from sim_holidays "
        "where study_id = $1 order by date",
        study_id,
    )


async def get_wbs_overrides(conn: asyncpg.connection.Connection, study_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "select cycle_id, predecessor_id from sim_wbs_overrides where study_id = $1",
        study_id,
    )


async def create_study(
    conn: asyncpg.connection.Connection, project_id: UUID, name: str, start_date: date
) -> UUID:
    async with conn.transaction():
        study_id = await conn.fetchval(
            "insert into sim_studies (project_id, name, start_date) values ($1, $2, $3) returning id",
            project_id, name, start_date,
        )
        national_holidays = generate_national_holidays(start_date.year, _HOLIDAY_YEARS_WINDOW)
        for holiday_date, description in national_holidays:
            await conn.execute(
                "insert into sim_holidays (study_id, date, description, is_national) "
                "values ($1, $2, $3, true) on conflict (study_id, date) do nothing",
                study_id, holiday_date, description,
            )
    return study_id


async def update_study(
    conn: asyncpg.connection.Connection,
    study_id: UUID,
    name: str,
    start_date: date,
    holidays: list[HolidayInput],
) -> None:
    async with conn.transaction():
        await conn.execute(
            "update sim_studies set name = $1, start_date = $2 where id = $3",
            name, start_date, study_id,
        )
        await conn.execute("delete from sim_holidays where study_id = $1", study_id)
        for holiday in holidays:
            await conn.execute(
                "insert into sim_holidays (study_id, date, description, is_national) values ($1, $2, $3, $4)",
                study_id, holiday.date, holiday.description, holiday.is_national,
            )


async def delete_study(conn: asyncpg.connection.Connection, study_id: UUID) -> None:
    await conn.execute("delete from sim_studies where id = $1", study_id)


async def replace_cycles(
    conn: asyncpg.connection.Connection,
    study_id: UUID,
    services: list[ServiceInput],
    floors: list[FloorInput],
    cycles: list[CycleInput],
) -> None:
    async with conn.transaction():
        service_ids = await _upsert_services(conn, study_id, services)
        floor_ids = await _upsert_floors(conn, study_id, floors)
        await _upsert_cycles(conn, study_id, service_ids, floor_ids, cycles)


async def _upsert_services(
    conn: asyncpg.connection.Connection, study_id: UUID, services: list[ServiceInput]
) -> list[UUID]:
    kept_ids: list[UUID] = []
    for service in services:
        if service.id is not None:
            await conn.execute(
                "update sim_services set name = $1, color = $2, order_index = $3, lag_days = $4 "
                "where id = $5 and study_id = $6",
                service.name, service.color, service.order_index, service.lag_days, service.id, study_id,
            )
            kept_ids.append(service.id)
        else:
            new_id = await conn.fetchval(
                "insert into sim_services (study_id, name, color, order_index, lag_days) "
                "values ($1, $2, $3, $4, $5) returning id",
                study_id, service.name, service.color, service.order_index, service.lag_days,
            )
            kept_ids.append(new_id)

    await conn.execute(
        "delete from sim_services where study_id = $1 and id != all($2::uuid[])", study_id, kept_ids
    )
    return kept_ids


async def _upsert_floors(
    conn: asyncpg.connection.Connection, study_id: UUID, floors: list[FloorInput]
) -> list[UUID]:
    kept_ids: list[UUID] = []
    for floor in floors:
        if floor.id is not None:
            await conn.execute(
                "update sim_floors set group_name = $1, floor_name = $2, order_index = $3 "
                "where id = $4 and study_id = $5",
                floor.group_name, floor.floor_name, floor.order_index, floor.id, study_id,
            )
            kept_ids.append(floor.id)
        else:
            new_id = await conn.fetchval(
                "insert into sim_floors (study_id, group_name, floor_name, order_index) "
                "values ($1, $2, $3, $4) returning id",
                study_id, floor.group_name, floor.floor_name, floor.order_index,
            )
            kept_ids.append(new_id)

    await conn.execute(
        "delete from sim_floors where study_id = $1 and id != all($2::uuid[])", study_id, kept_ids
    )
    return kept_ids


async def _upsert_cycles(
    conn: asyncpg.connection.Connection,
    study_id: UUID,
    service_ids: list[UUID],
    floor_ids: list[UUID],
    cycles: list[CycleInput],
) -> None:
    kept_ids: list[UUID] = []
    for cycle in cycles:
        service_id = service_ids[cycle.service_index]
        floor_id = floor_ids[cycle.floor_index]
        cycle_id = await conn.fetchval(
            "insert into sim_cycles (study_id, service_id, floor_id, duration_days) "
            "values ($1, $2, $3, $4) "
            "on conflict (service_id, floor_id) do update set duration_days = excluded.duration_days "
            "returning id",
            study_id, service_id, floor_id, cycle.duration_days,
        )
        kept_ids.append(cycle_id)

    # Cascade de sim_cycles pra sim_wbs_overrides cuida de limpar predecessores
    # que apontavam pra um ciclo removido aqui (célula que o usuário apagou).
    await conn.execute(
        "delete from sim_cycles where study_id = $1 and id != all($2::uuid[])", study_id, kept_ids
    )


async def replace_wbs_overrides(
    conn: asyncpg.connection.Connection, study_id: UUID, overrides: list[WbsOverrideInput]
) -> None:
    async with conn.transaction():
        await conn.execute("delete from sim_wbs_overrides where study_id = $1", study_id)
        for override in overrides:
            for predecessor_id in override.predecessor_ids:
                await conn.execute(
                    "insert into sim_wbs_overrides (study_id, cycle_id, predecessor_id) "
                    "values ($1, $2, $3) on conflict (cycle_id, predecessor_id) do nothing",
                    study_id, override.cycle_id, predecessor_id,
                )
