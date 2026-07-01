"""Cliente Supabase compartilhado — usado tanto por storage (upload do .mpp
original) quanto por core/security.py (validação do JWT do Supabase Auth).

Mesmo padrão de infra/db/pool.py: iniciado uma vez no lifespan do FastAPI,
encerrado no shutdown.
"""
from __future__ import annotations

from supabase import AsyncClient, create_async_client

from app.core.config import get_settings

_client: AsyncClient | None = None


async def init_supabase_client() -> None:
    """Cria o cliente Supabase. Idempotente."""
    global _client
    if _client is not None:
        return
    settings = get_settings()
    _client = await create_async_client(settings.supabase_url, settings.supabase_service_role_key)


def close_supabase_client() -> None:
    """Libera a referência do cliente Supabase. Idempotente.

    AsyncClient (supabase-py) não expõe um close() explícito — os clientes
    HTTP internos (auth/storage/postgrest) são coletados pelo GC junto com
    o objeto.
    """
    global _client
    _client = None


def get_supabase_client() -> AsyncClient:
    if _client is None:
        raise RuntimeError(
            "Cliente Supabase não está iniciado — init_supabase_client() deve ser "
            "chamado no lifespan do FastAPI."
        )
    return _client
