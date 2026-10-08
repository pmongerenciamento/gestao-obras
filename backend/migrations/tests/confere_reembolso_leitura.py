"""Conferência SOMENTE LEITURA do módulo de reembolso, em staging ou em produção.
Responde às dúvidas da auditoria de 2026-10-07 sem gravar nada:
  1. cost_centers ainda existe (tabela ou view) ou só expense_categories (034)?
     Para qual tabela aponta a FK de reimbursement_items.cost_center_id?
  2. Categorias de despesa e taxas vigentes (reimbursement_rate_rules).
  3. Relatórios por status e itens por tipo; itens sem regra de rateio.
  4. Times, membros por time e perfis sem time; perfis sem full_name;
     perfis por papel e por módulo; regras de rateio e soma das fatias.
  5. Policies de RLS das tabelas do reembolso (o buraco do DELETE de itens) e
     privilégio de DELETE do authenticated em reimbursement_items.
  6. Funções usadas pelo módulo e buckets do Storage (há onde guardar
     comprovante?).
Travas: host e ref do alvo conferidos ANTES de conectar; transação READ ONLY.
Nunca imprime DSN, e-mail nem id de pessoa: só contagens, nomes de tabela,
policy, categoria, time, regra e bucket.
Uso: PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe <arquivo> staging|prod
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

import _lib

BACKEND = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
STAGING_REF, PROD_REF = "gesqstdtbbdhlravddhd", "ttqtefwntkgpgatrcyps"
TARGETS = {"staging": (BACKEND / ".env.staging", "us-west-2", STAGING_REF, PROD_REF),
           "prod": (BACKEND / ".env", "sa-east-1", PROD_REF, STAGING_REF)}
REIMB_TABLES = ["reimbursement_reports", "reimbursement_items", "reimbursement_rate_rules",
                "expense_categories", "allocation_rules", "allocation_rule_splits", "team_cost_allocations"]


def load_dsn(env, host, ref, other_ref):
    dsn = ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            dsn = line.split("=", 1)[1].strip().strip('"').strip("'")
    if host not in dsn or ref not in dsn or other_ref in dsn:
        sys.exit(f"ABORTADO: DATABASE_URL de {env.name} não passa na trava de host/ref")
    return dsn


def show(title, rows):
    print(f"\n== {title}")
    if not rows:
        print("   (nenhuma linha)")
    for r in rows:
        print("   " + " | ".join(f"{k}={v}" for k, v in r.items()))


async def main(target):
    env, host, ref, other = TARGETS[target]
    c = await asyncpg.connect(load_dsn(env, host, ref, other), ssl=_lib.ssl_ctx(target))
    try:
        async with c.transaction(readonly=True):
            print(f"[{target}] transaction_read_only = {await c.fetchval('show transaction_read_only')}")

            # 1. cost_centers x expense_categories
            show("1a. relações com esses nomes (tabela r, view v)", [dict(r) for r in await c.fetch(
                "select c.relname as nome, c.relkind as tipo from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' "
                "and c.relname in ('cost_centers', 'expense_categories') order by 1")])
            show("1b. FK de reimbursement_items.cost_center_id aponta para", [dict(r) for r in await c.fetch(
                "select conname as constraint, confrelid::regclass::text as tabela from pg_constraint "
                "where conrelid = 'public.reimbursement_items'::regclass and contype = 'f' "
                "and conkey = array[(select attnum from pg_attribute where attrelid = "
                "'public.reimbursement_items'::regclass and attname = 'cost_center_id')]::int2[]")])

            # 2. categorias e taxas
            show("2a. categorias de despesa (expense_categories)", [dict(r) for r in await c.fetch(
                "select name as categoria from public.expense_categories order by name")])
            show("2b. taxas (reimbursement_rate_rules)", [dict(r) for r in await c.fetch(
                "select type as tipo, value as valor, unit as unidade, auto_readjust as reajuste_auto, "
                "effective_start_date as inicio, effective_end_date as fim from public.reimbursement_rate_rules "
                "order by type, effective_start_date")])

            # 3. relatórios e itens
            show("3a. relatórios por status", [dict(r) for r in await c.fetch(
                "select status, count(*) as qtd from public.reimbursement_reports group by status order by status")])
            show("3b. itens por tipo", [dict(r) for r in await c.fetch(
                "select type as tipo, count(*) as qtd, sum(total_amount) as total from public.reimbursement_items "
                "group by type order by type")])
            show("3c. itens sem regra de rateio / sem categoria nem projeto", [dict(r) for r in await c.fetch(
                "select count(*) filter (where allocation_rule_id is null) as sem_regra, "
                "count(*) filter (where cost_center_id is null and project_id is null) as sem_categoria_nem_projeto, "
                "count(*) as total_itens from public.reimbursement_items")])

            # 4. times, perfis, módulos, regras
            show("4a. membros por time", [dict(r) for r in await c.fetch(
                "select t.name as time, count(tm.profile_id) as membros from public.teams t "
                "left join public.team_members tm on tm.team_id = t.id group by t.name order by t.name")])
            show("4b. perfis", [dict(r) for r in await c.fetch(
                "select count(*) as perfis, "
                "count(*) filter (where p.full_name is null or btrim(p.full_name) = '') as sem_full_name, "
                "count(*) filter (where not exists (select 1 from public.team_members tm "
                "where tm.profile_id = p.id)) as sem_time, "
                "count(*) filter (where p.system_role = 'master') as masters from public.profiles p")])
            show("4c. perfis por módulo", [dict(r) for r in await c.fetch(
                "select module as modulo, count(*) as perfis from public.profile_modules group by module order by module")])
            show("4d. perfis sem nenhum módulo", [dict(r) for r in await c.fetch(
                "select count(*) as perfis from public.profiles p where not exists "
                "(select 1 from public.profile_modules pm where pm.profile_id = p.id)")])
            show("4e. regras de rateio e soma das fatias", [dict(r) for r in await c.fetch(
                "select r.name as regra, count(s.id) as fatias, coalesce(sum(s.percentage), 0) as soma "
                "from public.allocation_rules r left join public.allocation_rule_splits s on s.rule_id = r.id "
                "group by r.name order by r.name")])

            # 5. RLS e privilégios
            show("5a. RLS ligada", [dict(r) for r in await c.fetch(
                "select c.relname as tabela, c.relrowsecurity as rls from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' "
                "and c.relname = any($1::text[]) order by 1", REIMB_TABLES)])
            show("5b. policies", [dict(r) for r in await c.fetch(
                "select tablename as tabela, policyname as policy, cmd as comando from pg_policies "
                "where schemaname = 'public' and tablename = any($1::text[]) order by tablename, policyname",
                REIMB_TABLES)])
            show("5c. authenticated com DELETE em reimbursement_items / reimbursement_reports", [dict(r) for r in await c.fetch(
                "select has_table_privilege('authenticated', 'public.reimbursement_items', 'DELETE') as itens, "
                "has_table_privilege('authenticated', 'public.reimbursement_reports', 'DELETE') as relatorios")])

            # 6. funções e Storage
            show("6a. funções usadas pelo módulo", [dict(r) for r in await c.fetch(
                "select f as funcao, to_regprocedure(f) is not null as existe from unnest(array["
                "'public.default_allocation_rule_for_profile(uuid)', 'public.profile_display_name(uuid)', "
                "'public.has_permission(text, text)']) f")])
            show("6b. buckets do Storage", [dict(r) for r in await c.fetch(
                "select name as bucket, public as publico from storage.buckets order by name")])
    finally:
        await c.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TARGETS:
        sys.exit("uso: ... staging|prod")
    asyncio.run(main(sys.argv[1]))
