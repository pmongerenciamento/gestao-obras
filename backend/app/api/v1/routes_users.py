"""Rotas de gestão de usuários: listar, convidar, bloquear/desbloquear/resetar
senha e excluir. Restritas ao usuário master (ver app/core/roles.py) — o
frontend também esconde essa tela de não-masters, mas a checagem que importa
de verdade é esta aqui.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from supabase_auth.errors import AuthError

from app.core.dependencies import get_current_master_user, get_db
from app.domain.users import create_user, delete_user, list_users, update_user
from app.infra.storage import get_supabase_client
from app.schemas import CreateUserRequest, UserActionRequest, UserOut

router = APIRouter()


def _raise_auth_error(exc: AuthError) -> None:
    # Erros do Supabase Auth (e-mail inválido, rate limit, etc) — repassa a
    # mensagem e o status HTTP originais em vez de virar 500 genérico.
    status_code = getattr(exc, "status", 502) or 502
    raise HTTPException(status_code=status_code, detail=exc.message) from exc


@router.get("/users")
async def get_users(
    _master_id: UUID = Depends(get_current_master_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> list[UserOut]:
    return await list_users(conn)


@router.post("/users", status_code=201)
async def post_user(
    body: CreateUserRequest,
    master_id: UUID = Depends(get_current_master_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> UserOut:
    try:
        return await create_user(
            conn, get_supabase_client(), master_id, body.email, body.full_name, body.project_ids
        )
    except AuthError as exc:
        _raise_auth_error(exc)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: UUID,
    body: UserActionRequest,
    master_id: UUID = Depends(get_current_master_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> UserOut:
    try:
        return await update_user(
            conn, get_supabase_client(), user_id, body.action, body.project_id,
            granted_by=master_id, avatar_url=body.avatar_url,
        )
    except AuthError as exc:
        _raise_auth_error(exc)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(
    user_id: UUID,
    _master_id: UUID = Depends(get_current_master_user),
) -> Response:
    try:
        await delete_user(get_supabase_client(), user_id)
    except AuthError as exc:
        _raise_auth_error(exc)
    return Response(status_code=204)
