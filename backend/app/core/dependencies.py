"""Dependencies do FastAPI: get_current_user, get_db, etc."""
from __future__ import annotations

from typing import AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import require_master, verify_token
from app.infra.db.pool import get_pool

_bearer_scheme = HTTPBearer()


async def get_db() -> AsyncIterator[asyncpg.connection.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> UUID:
    user = await verify_token(credentials.credentials)
    return user.id


async def get_current_master_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> UUID:
    user = await verify_token(credentials.credentials)
    require_master(user)
    return user.id
