"""Pool de conexões asyncpg compartilhado pela aplicação.

Iniciado uma vez no startup (lifespan do FastAPI) e encerrado no shutdown,
no mesmo padrão usado para a JVM do MPXJ (ver app/infra/mpxj/jvm.py).
"""
from __future__ import annotations

import logging

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Cria o pool de conexões. Idempotente."""
    global _pool
    if _pool is not None:
        return
    settings = get_settings()
    _pool = await asyncpg.create_pool(dsn=settings.database_url)
    logger.info("Pool asyncpg iniciado")


async def close_pool() -> None:
    """Fecha o pool de conexões. Idempotente."""
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None
    logger.info("Pool asyncpg encerrado")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Pool asyncpg não inicializado — init_pool() deve ser chamado no lifespan do FastAPI."
        )
    return _pool
