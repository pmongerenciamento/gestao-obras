"""Sugestão automática de conciliação: bank_transactions x expenses.

Nunca concilia sozinho — só marca como 'sugerido' (com match_confidence)
quando há exatamente um candidato; a confirmação ('conciliado') é sempre
manual, feita pelo financeiro.

Regras (decididas em 2026-10-04):
  - Só transações 'pendente' de débito (despesa é dinheiro que sai).
  - Despesa "ocupada" (já é matched_expense_id de uma transação
    'sugerido' ou 'conciliado') não é candidata.
  - Base dos dois níveis: valor exato E data da transação a até ±10 dias
    da data de referência da despesa (payment_date, senão due_date, senão
    o 1º dia de competencia_month) — sem a janela, um contrato recorrente
    (mesmo valor todo mês) empataria sempre.
  - ALTO: base + despesa ligada a vendor_contract cujo CNPJ (só dígitos)
    é igual ao payer_document da transação (só dígitos).
  - MÉDIO: base + nome do fornecedor contido na description ou no
    payer_name da transação (minúsculas, sem acento via translate()).
    Sem pg_trgm: a extensão não está instalada e não entra sem aprovação.
  - Precedência ALTO -> MÉDIO; empate (2+ candidatos) num nível deixa a
    transação 'pendente' — empate no ALTO NÃO cai pro MÉDIO.
  - Se a mesma despesa seria a única sugestão de 2+ transações da mesma
    rodada, nenhuma recebe — o resultado não depende da ordem.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

import asyncpg

_DATE_WINDOW_DAYS = 10

# Minúsculas e sem acento, sem depender da extensão unaccent.
_NORM = (
    "translate(lower(coalesce({0}, '')), "
    "'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc')"
)

_CANDIDATES_SQL = f"""
with tx as (
  select id, value, transaction_date, payer_document, payer_name, description
  from public.bank_transactions
  where reconciliation_status = 'pendente' and type = 'debito'
),
free_expenses as (
  select e.id, e.value, e.vendor_name, e.vendor_contract_id,
         coalesce(e.payment_date, e.due_date,
                  date_trunc('month', e.competencia_month)::date) as ref_date
  from public.expenses e
  where not exists (
    select 1 from public.bank_transactions b
    where b.matched_expense_id = e.id
      and b.reconciliation_status in ('sugerido', 'conciliado')
  )
)
select
  tx.id as tx_id,
  fe.id as expense_id,
  (fe.vendor_contract_id is not null
   and regexp_replace(coalesce(tx.payer_document, ''), '\\D', '', 'g') <> ''
   and regexp_replace(tx.payer_document, '\\D', '', 'g')
       = regexp_replace(coalesce(vc.cnpj, ''), '\\D', '', 'g')) as is_alto,
  (length(trim(fe.vendor_name)) > 0
   and (strpos({_NORM.format('tx.description')}, {_NORM.format('trim(fe.vendor_name)')}) > 0
        or strpos({_NORM.format('tx.payer_name')}, {_NORM.format('trim(fe.vendor_name)')}) > 0)) as is_medio
from tx
join free_expenses fe
  on fe.value = tx.value
 and abs(tx.transaction_date - fe.ref_date) <= {_DATE_WINDOW_DAYS}
left join public.vendor_contracts vc on vc.id = fe.vendor_contract_id
"""


def _decide(alto: list[UUID], medio: list[UUID]) -> tuple[UUID, str] | None:
    if len(alto) == 1:
        return alto[0], "alto"
    if len(alto) >= 2:
        return None  # empate no ALTO: não cai pro MÉDIO
    if len(medio) == 1:
        return medio[0], "medio"
    return None  # sem candidato ou empate no MÉDIO


async def suggest_matches(conn: asyncpg.connection.Connection) -> dict[str, int]:
    """Gera sugestões de conciliação pras transações pendentes de débito.
    Tudo numa transação só; nunca grava 'conciliado'."""
    async with conn.transaction():
        tx_ids = [r["id"] for r in await conn.fetch(
            "select id from public.bank_transactions "
            "where reconciliation_status = 'pendente' and type = 'debito'"
        )]

        alto: dict[UUID, list[UUID]] = defaultdict(list)
        medio: dict[UUID, list[UUID]] = defaultdict(list)
        for row in await conn.fetch(_CANDIDATES_SQL):
            if row["is_alto"]:
                alto[row["tx_id"]].append(row["expense_id"])
            if row["is_medio"]:
                medio[row["tx_id"]].append(row["expense_id"])

        decisions = {}
        for tx_id in tx_ids:
            decision = _decide(alto[tx_id], medio[tx_id])
            if decision is not None:
                decisions[tx_id] = decision

        # Mesma despesa como única sugestão de 2+ transações: nenhuma recebe.
        uses = Counter(expense_id for expense_id, _ in decisions.values())
        decisions = {t: d for t, d in decisions.items() if uses[d[0]] == 1}

        counts = {"alto": 0, "medio": 0}
        for tx_id, (expense_id, level) in decisions.items():
            status = await conn.execute(
                """
                update public.bank_transactions
                set reconciliation_status = 'sugerido',
                    match_confidence = $2,
                    matched_expense_id = $3
                where id = $1 and reconciliation_status = 'pendente'
                """,
                tx_id, level, expense_id,
            )
            if status == "UPDATE 1":
                counts[level] += 1

    return {
        "processadas": len(tx_ids),
        "alto": counts["alto"],
        "medio": counts["medio"],
        "pendentes": len(tx_ids) - counts["alto"] - counts["medio"],
    }
