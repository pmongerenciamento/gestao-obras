"""Comando manual: sincroniza o extrato do Banco Inter em bank_transactions.

    python -m app.cli.sync_extrato [--dias 3] [--env-file .env.staging]

Sem --env-file usa o DATABASE_URL do backend/.env (hoje: produção).
Temporário, pra teste manual — o agendamento automático vem depois.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, timedelta

from dotenv import dotenv_values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dias", type=int, default=3, help="dias pra trás, incluindo hoje")
    parser.add_argument("--env-file", help="arquivo de onde ler o DATABASE_URL (ex.: .env.staging)")
    return parser.parse_args()


async def _main(dias: int) -> None:
    # Imports aqui dentro: get_settings() é cacheado e precisa ler o
    # DATABASE_URL só depois do --env-file ter sido aplicado.
    from app.infra.db import close_pool, get_pool, init_pool
    from app.integrations.banco_inter import sync_extrato

    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=dias - 1)
    await init_pool()
    try:
        async with get_pool().acquire() as conn:
            host = conn._addr[0]
            print(f"banco: {host} | período: {data_inicio} a {data_fim}")
            print(await sync_extrato(conn, data_inicio, data_fim))
    finally:
        await close_pool()


if __name__ == "__main__":
    args = _parse_args()
    if args.env_file:
        os.environ["DATABASE_URL"] = dotenv_values(args.env_file)["DATABASE_URL"]
    asyncio.run(_main(args.dias))
