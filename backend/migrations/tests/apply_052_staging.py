"""Aplica a 052 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_052_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 051 está aplicada (contracts.billing_entity_id existe).
  5. A 052 ainda não está aplicada (reimbursement_items.receipt_path ausente,
     regra 'Time Diego/Murillo 100%' inexistente e
     fn_reimbursement_items_validate_total inexistente).
  6. O time 'Diego/Murillo' existe (senão a própria 052 aborta no item 6a).
Antes de gravar mede: contagem + md5 (linha inteira, ordenada por id) de
reimbursement_reports, reimbursement_items (sem receipt_path),
reimbursement_rate_rules, expense_categories, allocation_rules (sem a regra
nova), allocation_rule_splits (sem a fatia da regra nova), teams e
team_members; e os gatilhos que já existem em reimbursement_items e
reimbursement_reports (nome e se estão ligados).
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.
Os testes funcionais (P, G, V, C, D, E do test_052_staging.py) não se repetem
aqui: já passaram 79/79 dentro de transação desfeita. Aqui só estrutura e dados.

Verificações esperadas na conexão nova: 23
  V1 reimbursement_items: só as 4 policies novas, uma por comando 1
  + V2 reimbursement_reports_own com is_master 1
  + V3 reimbursement_reports_approve: is_master, 'enviado' e a regra de
       approved_by (exceto rejeição) 1
  + V4 trg_reimbursement_reports_guard_approval: tipo 19, ligado, função certa 1
  + V5 trg_reimbursement_items_validate_total: tipo 23, ligado, função certa,
       UPDATE OF as colunas de valor 1
  + V6 função com search_path vazio x 3 funções 3
  + V7 EXECUTE: funções de gatilho sem anon, PUBLIC e authenticated x 2;
       default_allocation_rule_for_profile só para authenticated x 1 3
  + V8 reimbursement_items.receipt_path: text, nula, sem padrão 1
  + V9 regra 'Time Diego/Murillo 100%' com uma única fatia, 100% para o time 1
  + V10 default_allocation_rule_for_profile com Diego/Murillo e sem o
        fallback 'Rateio Sócios 50/50' 1
  + V11 gatilhos que já existiam continuam ligados e só os 2 novos foram
        acrescentados 1
  = 15
  + D1 tabela igual ao começo (contagem + md5) x 8 tabelas 8
  = 23
"""
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "052_reembolso_fixes.sql"
REQUIRED_HOST = "us-west-2"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
DM_RULE = "Time Diego/Murillo 100%"
GUARD_FN = "public.fn_reimbursement_reports_guard_approval()"
TOTAL_FN = "public.fn_reimbursement_items_validate_total()"
ALLOC_FN = "public.default_allocation_rule_for_profile(uuid)"
# (nome, tabela, função, tgtype): 19 = ROW + BEFORE + UPDATE; 23 = ROW + BEFORE + INSERT + UPDATE
NEW_TRIGGERS = [("trg_reimbursement_reports_guard_approval", "public.reimbursement_reports", GUARD_FN, 19),
                ("trg_reimbursement_items_validate_total", "public.reimbursement_items", TOTAL_FN, 23)]
TRIGGERS_SQL = ("select tgrelid::regclass::text || '.' || tgname::text as name, tgenabled::text as enabled "
                "from pg_trigger where tgrelid in ('public.reimbursement_items'::regclass, "
                "'public.reimbursement_reports'::regclass) and not tgisinternal order by 1")
# (chave, origem com alias x, expressão da linha)
TABLES = [("reimbursement_reports", "public.reimbursement_reports x", "to_jsonb(x)"),
          ("reimbursement_items", "public.reimbursement_items x", "(to_jsonb(x) - 'receipt_path')"),
          ("reimbursement_rate_rules", "public.reimbursement_rate_rules x", "to_jsonb(x)"),
          ("expense_categories", "public.expense_categories x", "to_jsonb(x)"),
          ("allocation_rules", f"public.allocation_rules x where x.name <> '{DM_RULE}'", "to_jsonb(x)"),
          ("allocation_rule_splits", "public.allocation_rule_splits x where x.rule_id not in "
                                     f"(select id from public.allocation_rules where name = '{DM_RULE}')",
           "to_jsonb(x)"),
          ("teams", "public.teams x", "to_jsonb(x)"),
          ("team_members", "public.team_members x", "to_jsonb(x)")]

results = []


def abort(msg):
    print(f"ABORTADO: {msg}")
    sys.exit(2)


def record(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK     ' if ok else 'FALHOU '} {name}{' -- ' + detail if detail and not ok else ''}")


def load_dsn():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    abort("DATABASE_URL não encontrado em backend/.env.staging")


async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


def fmt(fp):
    return f"{fp[0]} (md5 {fp[1][:12]}…)"


async def fingerprints(c):
    out = {}
    for key, source, expr in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.id), '')) as h "
            f"from {source}")
        out[key] = (row["n"], row["h"])
    return out


async def triggers(c):
    return {r["name"]: r["enabled"] for r in await c.fetch(TRIGGERS_SQL)}


# ---------- travas + medição + aplicação ----------
async def apply(dsn, sql):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        num = int(await c.fetchval("show server_version_num"))
        print(f"server_version_num: {num}")
        if num < 150000:
            abort("Postgres anterior ao 15")
        if not await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                                "and table_name = 'contracts' and column_name = 'billing_entity_id')"):
            abort("a 051 não está aplicada (contracts.billing_entity_id ausente)")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'reimbursement_items' and column_name = 'receipt_path') "
                            "or exists (select 1 from public.allocation_rules where name = $1::text) "
                            "or to_regprocedure($2::text) is not null", DM_RULE, TOTAL_FN):
            abort("a 052 parece já aplicada (receipt_path, a regra Diego/Murillo ou a função de total existe)")
        if not await c.fetchval("select exists (select 1 from public.teams where name = 'Diego/Murillo')"):
            abort("o time 'Diego/Murillo' não existe: a 052 abortaria no item 6a")

        before = await fingerprints(c)
        before["triggers"] = await triggers(c)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in TABLES)
              + f"; gatilhos: {sorted(before['triggers'])}")

        async with c.transaction():
            await c.execute(sql)
        print("\n052 aplicada e COMMIT feito.\n")
        return before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify_structure(c, before):
    await check(c, "V1 reimbursement_items: só as 4 policies novas, uma por comando",
                "select string_agg(policyname::text || ':' || cmd::text, ',' order by policyname) from pg_policies "
                "where schemaname = 'public' and tablename = 'reimbursement_items'",
                "reimbursement_items_delete:DELETE,reimbursement_items_insert:INSERT,"
                "reimbursement_items_select:SELECT,reimbursement_items_update:UPDATE")
    await check(c, "V2 reimbursement_reports_own com is_master",
                "select qual like '%is_master()%' from pg_policies where schemaname = 'public' "
                "and tablename = 'reimbursement_reports' and policyname = 'reimbursement_reports_own'", True)
    await check(c, "V3 reimbursement_reports_approve: is_master, só de 'enviado', approved_by exigido fora da rejeição",
                "select qual like '%is_master()%' and qual like '%''enviado''%' and qual not like '%has_permission%' "
                "and with_check like '%is_master()%' and with_check like '%approved_by = auth.uid()%' "
                "and with_check like '%''rejeitado''%' from pg_policies where schemaname = 'public' "
                "and tablename = 'reimbursement_reports' and policyname = 'reimbursement_reports_approve'", True)
    await check(c, "V4 trg_reimbursement_reports_guard_approval: BEFORE UPDATE, por linha, ligado, função certa",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_reports_guard_approval' "
                "and tgrelid = 'public.reimbursement_reports'::regclass and tgtype = 19 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text)", 1, GUARD_FN)
    await check(c, "V5 trg_reimbursement_items_validate_total: BEFORE INSERT OR UPDATE OF as colunas de valor",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_items_validate_total' "
                "and tgrelid = 'public.reimbursement_items'::regclass and tgtype = 23 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text) and pg_get_triggerdef(oid) like '%UPDATE OF type, "
                "expense_date, km_traveled, km_rate, toll_amount, other_amount, total_amount ON "
                "public.reimbursement_items%'", 1, TOTAL_FN)
    for fn in (GUARD_FN, TOTAL_FN, ALLOC_FN):
        await check(c, f"V6 {fn} com search_path vazio",
                    "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                    "from pg_proc where oid = to_regprocedure($1::text)", True, fn)
    no_public = ("not exists (select 1 from pg_proc p, aclexplode(p.proacl) a where p.oid = to_regprocedure($1::text) "
                 "and a.grantee = 0 and a.privilege_type = 'EXECUTE')")
    for fn in (GUARD_FN, TOTAL_FN):
        await check(c, f"V7 {fn}: sem EXECUTE para anon, PUBLIC e authenticated",
                    "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                    f"and not has_function_privilege('authenticated'::name, $1::text, 'execute') and {no_public}",
                    True, fn)
    await check(c, f"V7 {ALLOC_FN}: EXECUTE só para authenticated (sem anon e PUBLIC)",
                "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                f"and has_function_privilege('authenticated'::name, $1::text, 'execute') and {no_public}",
                True, ALLOC_FN)
    got = await c.fetchrow("select data_type::text, is_nullable::text, column_default::text "
                           "from information_schema.columns where table_schema = 'public' "
                           "and table_name = 'reimbursement_items' and column_name = 'receipt_path'")
    got = tuple(got) if got else None
    record("V8 reimbursement_items.receipt_path: text, aceita nulo, sem padrão", got == ("text", "YES", None),
           f"veio {got!r}")
    await check(c, f"V9 '{DM_RULE}' com uma única fatia, 100% para o time Diego/Murillo",
                "select count(*) = 1 and bool_and(s.percentage = 100 and t.name = 'Diego/Murillo') "
                "from public.allocation_rule_splits s join public.allocation_rules r on r.id = s.rule_id "
                "join public.teams t on t.id = s.team_id where r.name = $1::text", True, DM_RULE)
    await check(c, "V10 default_allocation_rule_for_profile com Diego/Murillo e sem o fallback 'Rateio Sócios 50/50'",
                "select prosrc like '%Time Diego/Murillo 100%%' and prosrc not like '%Rateio Sócios%' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, ALLOC_FN)
    after = await triggers(c)
    kept = all(after.get(n) == "O" for n in before["triggers"])
    extra = sorted(set(after) - set(before["triggers"]))
    expected_extra = sorted(f"{table.split('.')[1]}.{name}" for name, table, _, _ in NEW_TRIGGERS)
    record("V11 gatilhos que já existiam continuam ligados, e só os 2 novos foram acrescentados",
           kept and extra == expected_extra, f"antes {sorted(before['triggers'])}, depois {sorted(after)}")


async def verify(dsn, before):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            await verify_structure(c, before)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for key, _, _ in TABLES:
                record(f"D1 {key}: igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
    finally:
        await c.close()


async def main():
    dsn = load_dsn()
    if REQUIRED_HOST not in dsn:
        abort(f"DATABASE_URL não contém {REQUIRED_HOST}: não é staging")
    if STAGING_REF not in dsn:
        abort("DATABASE_URL não contém a ref de staging")
    if PROD_REF in dsn:
        abort("DATABASE_URL contém a ref de PRODUÇÃO")

    sql = MIGRATION.read_text(encoding="utf-8")
    if re.search(r"^\s*(begin|commit|rollback)\s*;", sql, re.I | re.M):
        abort("a migration tem begin/commit/rollback no nível de topo")

    before = await apply(dsn, sql)
    await verify(dsn, before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
