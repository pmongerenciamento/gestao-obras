"""Rota TEMPORÁRIA pra validar a autenticação com o Banco Inter (OAuth2 +
mTLS). Restrita ao usuário master. Nunca devolve o token, só se a
autenticação funcionou. Remover quando a consulta de extrato existir.
"""
from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_master_user
from app.integrations.banco_inter import BancoInterConfigError, get_access_token

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/banco-inter/test-auth")
async def test_banco_inter_auth(
    _master_id: UUID = Depends(get_current_master_user),
) -> dict[str, bool]:
    try:
        await get_access_token()
    except BancoInterConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        # Só o status vai na resposta; o corpo do Inter fica no log do servidor.
        logger.warning(
            "Banco Inter recusou o token: %s %s", exc.response.status_code, exc.response.text
        )
        raise HTTPException(
            status_code=502,
            detail=f"Banco Inter recusou a autenticação (HTTP {exc.response.status_code})",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Falha de conexão com o Banco Inter: %r", exc)
        raise HTTPException(
            status_code=502, detail=f"Falha de conexão com o Banco Inter ({type(exc).__name__})"
        ) from exc
    return {"authenticated": True}
