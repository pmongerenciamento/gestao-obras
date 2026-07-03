"""Controle de acesso do usuário master.

Sem sistema de roles no banco ainda (gap registrado em docs/sessao-atual.md,
item 33) — mesma lista hardcoded de frontend/lib/auth/roles.ts, espelhada
aqui porque os endpoints de gestão de usuários são poderosos o bastante
(criar/bloquear/excluir contas) pra não poderem confiar só na checagem do
frontend.
"""
from __future__ import annotations

MASTER_EMAILS = ["diego@pmongerenciamento.com.br"]


def is_master(email: str) -> bool:
    return email.lower() in {master_email.lower() for master_email in MASTER_EMAILS}
