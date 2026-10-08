"""PROPOSTA (não executado): carga inicial de versões de divisão de receita
logo depois da 047, para que extend_recurring_installments não recuse
contratos mensais que já têm parcelas projetadas.

Uso (do repositório):
  backend/.venv/Scripts/python.exe backend/migrations/tests/carga_inicial_splits.py staging         -> simulação no staging
  backend/.venv/Scripts/python.exe backend/migrations/tests/carga_inicial_splits.py prod            -> simulação em produção
  backend/.venv/Scripts/python.exe backend/migrations/tests/carga_inicial_splits.py prod commit     -> grava em produção

O que faz:
- Lista contratos 'ativo' + 'mensal_recorrente' com parcelas origin =
  'projetada' e SEM nenhuma versão em contract_revenue_splits.
- Para cada um, grava UMA versão com valid_from = menor competencia_month das
  parcelas do contrato, fatia 'dono' 100% para projects.team_id e scope =
  tipo de receita da primeira parcela.
- Contrato cujo projeto não tem team_id NÃO é carregado: é listado para
  decisão manual (não há time dono a quem atribuir).
- A divisão 80/20 (fatia a_parte) é decisão do Diego por contrato e NÃO é
  inventada aqui: a carga só garante cobertura com 100% para o time dono;
  o ajuste vem depois, pela tela, com set_contract_splits.
- set_contract_splits exige auth.uid() e has_permission: o script faz SET
  LOCAL ROLE authenticated com o sub da conta do Diego (resolvida pelo
  e-mail, não impresso), que tem o módulo financeiro.
- Tudo numa transação; em simulação termina com ROLLBACK, com 'commit'
  termina com COMMIT só se nenhum contrato falhar.
Nunca imprime e-mails, DSN ou chaves.
"""
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

import _lib

REPO = Path(r"C:\Users\pmon_admin\Documents\gestao-obras")
TARGETS = {"staging": (REPO / "backend" / ".env.staging", "us-west-2", "gesqstdtbbdhlravddhd", "ttqtefwntkgpgatrcyps"),
           "prod": (REPO / "backend" / ".env", "sa-east-1", "ttqtefwntkgpgatrcyps", "gesqstdtbbdhlravddhd")}
MASTER_EMAIL = None  # preenchido por load_dsn() com MASTER_EMAIL do .env do alvo

CANDIDATES_SQL = """
select c.id as contract_id, p.team_id,
       min(i.competencia_month) as valid_from,
       (array_agg(i.revenue_type order by i.due_date, i.installment_number))[1] as scope
  from public.contracts c
  join public.projects p on p.id = c.project_id
  join public.contract_installments i on i.contract_id = c.id and i.origin = 'projetada'
 where c.status = 'ativo' and c.payment_type = 'mensal_recorrente'
   and not exists (select 1 from public.contract_revenue_splits s where s.contract_id = c.id)
 group by c.id, p.team_id
 order by c.id
"""


def load_dsn(target):
    global MASTER_EMAIL
    path, host, ref, other = TARGETS[target]
    dsn = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.strip().startswith("MASTER_EMAIL="):
            MASTER_EMAIL = line.split("=", 1)[1].strip().strip('"').strip("'")
    if host not in dsn or ref not in dsn or other in dsn:
        sys.exit(f"ABORTADO: DATABASE_URL não confere com {target}")
    if not MASTER_EMAIL or "@" not in MASTER_EMAIL:
        sys.exit(f"ABORTADO: MASTER_EMAIL ausente ou inválido no .env de {target}")
    return dsn


async def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        sys.exit("uso: carga_inicial_splits.py staging|prod [commit]")
    target, commit = sys.argv[1], len(sys.argv) > 2 and sys.argv[2] == "commit"
    dsn = load_dsn(target)
    c = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx(target))
    tr = c.transaction()
    await tr.start()
    finished = False
    try:
        if not await c.fetchval("select to_regprocedure('public.set_contract_splits(uuid, date, jsonb, boolean)') "
                                "is not null"):
            sys.exit("ABORTADO: a 047 não está aplicada")
        rows = await c.fetch("select id from auth.users where lower(email) = lower($1::text)", MASTER_EMAIL)
        if len(rows) != 1:
            sys.exit("ABORTADO: conta do Diego não encontrada (ou repetida)")
        diego = rows[0]["id"]

        cands = await c.fetch(CANDIDATES_SQL)
        print(f"{target}: {len(cands)} contrato(s) sem versão de divisão e com parcelas projetadas")
        sem_time = [r["contract_id"] for r in cands if r["team_id"] is None]
        loaded = 0
        for r in cands:
            if r["team_id"] is None:
                continue
            payload = json.dumps([{"share_kind": "dono", "team_id": str(r["team_id"]),
                                   "scope": r["scope"], "percentage": 100}])
            await c.execute("set local role authenticated")
            await c.fetchval("select set_config('request.jwt.claim.sub', $1::text, true), "
                             "set_config('request.jwt.claims', $2::text, true)",
                             str(diego), json.dumps({"sub": str(diego), "role": "authenticated"}))
            n = await c.fetchval("select public.set_contract_splits($1, $2, $3::jsonb, false)",
                                 r["contract_id"], r["valid_from"], payload)
            await c.execute("reset role")
            print(f"  contrato {r['contract_id']}: versão {r['valid_from']} gravada ({n} linha)")
            loaded += 1
        if sem_time:
            print(f"  {len(sem_time)} contrato(s) sem time no projeto, NÃO carregados (decisão manual): {sem_time}")
        await c.execute("set constraints all immediate")  # confere a soma 100 antes do fim
        if commit and not sem_time:
            await tr.commit()
            print(f"COMMIT: {loaded} versão(ões) gravada(s).")
        else:
            await tr.rollback()
            print(f"ROLLBACK ({'simulação' if not commit else 'há contratos sem time'}): {loaded} versão(ões) seriam gravadas.")
        finished = True
    except BaseException:
        if not finished:
            await tr.rollback()
        raise
    finally:
        await c.close()


if __name__ == "__main__":
    asyncio.run(main())
