"""Validação de JWT do Supabase Auth e funções relacionadas a autenticação/autorização."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from supabase_auth.errors import AuthError

from app.infra.storage import get_supabase_client


async def verify_token(token: str) -> UUID:
    """Valida um access token do Supabase Auth e devolve o id do usuário
    autenticado (owner_id). Levanta HTTPException(401) se o token for
    ausente, inválido ou expirado.
    """
    client = get_supabase_client()
    try:
        response = await client.auth.get_user(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado") from exc

    if response is None or response.user is None:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    return UUID(response.user.id)
