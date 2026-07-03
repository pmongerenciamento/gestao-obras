"""Acesso a dados do módulo Pré-planejamento via asyncpg.

replace_cycles/replace_holidays usam replace completo (delete + reinsert)
dentro de uma transação — a UI sempre manda o estado inteiro da grade/do
calendário (mesmo padrão de "salvar a planilha inteira" descrito no plano),
não patches incrementais.
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


@dataclass
class FloorInput:
    group_name: str
    floor_name: str
    order_index: int


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
        await conn.execute("delete from sim_links where study_id = $1", study_id)
        await conn.execute("delete from sim_cycles where study_id = $1", study_id)
        await conn.execute("delete from sim_services where study_id = $1", study_id)
        await conn.execute("delete from sim_floors where study_id = $1", study_id)

        service_ids: list[UUID] = []
        for service in services:
            service_id = await conn.fetchval(
                "insert into sim_services (study_id, name, color, order_index, lag_days) "
                "values ($1, $2, $3, $4, $5) returning id",
                study_id, service.name, service.color, service.order_index, service.lag_days,
            )
            service_ids.append(service_id)

        floor_ids: list[UUID] = []
        for floor in floors:
            floor_id = await conn.fetchval(
                "insert into sim_floors (study_id, group_name, floor_name, order_index) "
                "values ($1, $2, $3, $4) returning id",
                study_id, floor.group_name, floor.floor_name, floor.order_index,
            )
            floor_ids.append(floor_id)

        # cycle_id por (service_index, floor_index) — usado pra montar os vínculos em seguida.
        cycle_ids: dict[tuple[int, int], UUID] = {}
        for cycle in cycles:
            service_id = service_ids[cycle.service_index]
            floor_id = floor_ids[cycle.floor_index]
            cycle_id = await conn.fetchval(
                "insert into sim_cycles (study_id, service_id, floor_id, duration_days) "
                "values ($1, $2, $3, $4) returning id",
                study_id, service_id, floor_id, cycle.duration_days,
            )
            cycle_ids[(cycle.service_index, cycle.floor_index)] = cycle_id

        await _generate_links(conn, study_id, services, floors, cycles, cycle_ids)


async def _generate_links(
    conn: asyncpg.connection.Connection,
    study_id: UUID,
    services: list[ServiceInput],
    floors: list[FloorInput],
    cycles: list[CycleInput],
    cycle_ids: dict[tuple[int, int], UUID],
) -> None:
    """Encadeia, pra cada serviço dentro de cada grupo/torre, os pavimentos
    consecutivos (por order_index) que têm ciclo daquele serviço — torres
    diferentes têm sequências independentes (decisão do usuário).
    """
    cycles_by_service: dict[int, set[int]] = {}
    for cycle in cycles:
        cycles_by_service.setdefault(cycle.service_index, set()).add(cycle.floor_index)

    for service_index, floor_indices in cycles_by_service.items():
        lag_days = services[service_index].lag_days

        floors_by_group: dict[str, list[int]] = {}
        for floor_index in floor_indices:
            group_name = floors[floor_index].group_name
            floors_by_group.setdefault(group_name, []).append(floor_index)

        for group_floor_indices in floors_by_group.values():
            group_floor_indices.sort(key=lambda idx: floors[idx].order_index)
            for predecessor_floor, successor_floor in zip(group_floor_indices, group_floor_indices[1:]):
                predecessor_id = cycle_ids[(service_index, predecessor_floor)]
                successor_id = cycle_ids[(service_index, successor_floor)]
                await conn.execute(
                    "insert into sim_links (study_id, predecessor_id, successor_id, lag_days) "
                    "values ($1, $2, $3, $4)",
                    study_id, predecessor_id, successor_id, lag_days,
                )
