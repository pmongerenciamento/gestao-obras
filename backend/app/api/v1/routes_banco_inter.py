"""Rota TEMPORÁRIA pra validar a consulta de extrato do Banco Inter.
Restrita ao usuário master. Devolve só um resumo (quantidade e somas),
nunca as transações individuais — a rota ainda não teve revisão de
segurança completa. Remover quando a sincronização do extrato existir.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_master_user
from app.integrations.banco_inter import BancoInterConfigError, get_extrato

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/banco-inter/test-extrato")
async def test_banco_inter_extrato(
    _master_id: UUID = Depends(get_current_master_user),
) -> dict[str, int | str]:
    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=2)  # 3 dias, incluindo hoje
    try:
        transacoes = await get_extrato(data_inicio, data_fim)
    except BancoInterConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        # Só o status vai na resposta; o corpo do Inter fica no log do servidor.
        logger.warning(
            "Banco Inter recusou a consulta: %s %s", exc.response.status_code, exc.response.text
        )
        raise HTTPException(
            status_code=502,
            detail=f"Banco Inter recusou a consulta (HTTP {exc.response.status_code})",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Falha de conexão com o Banco Inter: %r", exc)
        raise HTTPException(
            status_code=502, detail=f"Falha de conexão com o Banco Inter ({type(exc).__name__})"
        ) from exc

    total_creditos = sum((t["value"] for t in transacoes if t["type"] == "credito"), Decimal(0))
    total_debitos = sum((t["value"] for t in transacoes if t["type"] == "debito"), Decimal(0))
    return {
        "periodo": f"{data_inicio.isoformat()} a {data_fim.isoformat()}",
        "quantidade": len(transacoes),
        "total_creditos": str(total_creditos),
        "total_debitos": str(total_debitos),
    }
