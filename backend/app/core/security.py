"""Validação de JWT do Supabase Auth e funções relacionadas a autenticação/autorização."""
from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

from fastapi import HTTPException
from supabase_auth.errors import AuthError

from app.core.roles import is_master
from app.infra.storage import get_supabase_client


class AuthenticatedUser(NamedTuple):
    id: UUID
    email: str


async def verify_token(token: str) -> AuthenticatedUser:
    """Valida um access token do Supabase Auth e devolve o id/e-mail do
    usuário autenticado. Levanta HTTPException(401) se o token for ausente,
    inválido ou expirado.
    """
    client = get_supabase_client()
    try:
        response = await client.auth.get_user(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado") from exc

    if response is None or response.user is None or response.user.email is None:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    return AuthenticatedUser(id=UUID(response.user.id), email=response.user.email)


def require_master(user: AuthenticatedUser) -> None:
    if not is_master(user.email):
        raise HTTPException(status_code=403, detail="Acesso restrito ao usuário master")
