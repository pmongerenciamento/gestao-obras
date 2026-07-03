"""Gestão de usuários: lista via SQL direto (auth.users é uma tabela Postgres
comum, a mesma conexão DATABASE_URL já enxerga — evita depender da paginação
da Admin API só pra listar). Escrita de conta (criar/bloquear/excluir) exige
a Admin API do Supabase Auth (client com service_role_key, ver
infra/storage/client.py) — não dá pra fazer via SQL puro (hash de senha,
identities, etc ficam por conta do GoTrue).
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from supabase import AsyncClient

from app.schemas.users import ProjectMembershipOut, UserOut

_BLOCK_DURATION = "876000h"  # ~100 anos — não existe "ban permanente" na Admin API, só duração


async def _fetch_users(
    conn: asyncpg.connection.Connection, user_id: UUID | None = None
) -> list[UserOut]:
    user_rows = await conn.fetch(
        """
        select u.id, u.email, u.created_at, u.email_confirmed_at, u.banned_until,
               p.full_name, p.avatar_url
        from auth.users u
        left join profiles p on p.id = u.id
        where $1::uuid is null or u.id = $1
        order by u.created_at desc
        """,
        user_id,
    )
    membership_rows = await conn.fetch(
        """
        select pm.user_id, pm.project_id, pr.name as project_name, pm.status
        from project_members pm
        join projects pr on pr.id = pm.project_id
        where $1::uuid is null or pm.user_id = $1
        """,
        user_id,
    )

    memberships_by_user: dict[UUID, list[ProjectMembershipOut]] = {}
    for row in membership_rows:
        memberships_by_user.setdefault(row["user_id"], []).append(
            ProjectMembershipOut(
                project_id=row["project_id"],
                project_name=row["project_name"],
                status=row["status"],
            )
        )

    return [
        UserOut(
            id=row["id"],
            email=row["email"],
            full_name=row["full_name"],
            avatar_url=row["avatar_url"],
            created_at=row["created_at"],
            email_confirmed_at=row["email_confirmed_at"],
            banned=row["banned_until"] is not None,
            memberships=memberships_by_user.get(row["id"], []),
        )
        for row in user_rows
    ]


async def list_users(conn: asyncpg.connection.Connection) -> list[UserOut]:
    return await _fetch_users(conn)


async def get_user(conn: asyncpg.connection.Connection, user_id: UUID) -> UserOut:
    users = await _fetch_users(conn, user_id)
    if not users:
        raise ValueError(f"Usuário {user_id} não encontrado")
    return users[0]


async def create_user(
    conn: asyncpg.connection.Connection,
    admin_client: AsyncClient,
    invited_by: UUID,
    email: str,
    full_name: str,
    project_ids: list[UUID],
) -> UserOut:
    response = await admin_client.auth.admin.invite_user_by_email(
        email, {"data": {"full_name": full_name}}
    )
    user_id = UUID(response.user.id)

    async with conn.transaction():
        await conn.execute("update profiles set full_name = $1 where id = $2", full_name, user_id)
        for project_id in project_ids:
            await conn.execute(
                "insert into project_members (project_id, user_id, invited_by, status) "
                "values ($1, $2, $3, 'pending')",
                project_id, user_id, invited_by,
            )

    return await get_user(conn, user_id)


async def update_user(
    conn: asyncpg.connection.Connection,
    admin_client: AsyncClient,
    user_id: UUID,
    action: str,
    project_id: UUID | None,
    granted_by: UUID | None = None,
    avatar_url: str | None = None,
) -> UserOut:
    if action == "reset_password":
        user = await get_user(conn, user_id)
        await admin_client.auth.reset_password_for_email(user.email)
    elif action == "set_avatar":
        await conn.execute("update profiles set avatar_url = $1 where id = $2", avatar_url, user_id)
    elif action == "grant":
        await conn.execute(
            "insert into project_members (project_id, user_id, invited_by, status) "
            "values ($1, $2, $3, 'active') "
            "on conflict (project_id, user_id) do nothing",
            project_id, user_id, granted_by,
        )
    elif project_id is not None:
        new_status = "blocked" if action == "block" else "active"
        await conn.execute(
            "update project_members set status = $1 where project_id = $2 and user_id = $3",
            new_status, project_id, user_id,
        )
    else:
        ban_duration = _BLOCK_DURATION if action == "block" else "none"
        await admin_client.auth.admin.update_user_by_id(str(user_id), {"ban_duration": ban_duration})

    return await get_user(conn, user_id)


async def delete_user(admin_client: AsyncClient, user_id: UUID) -> None:
    await admin_client.auth.admin.delete_user(str(user_id))
