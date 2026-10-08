"""Aplica a 049 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_049_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 047 está aplicada (valid_from existe, só a assinatura nova de
     set_contract_splits existe) e a 048 também (regra do master no corpo).
  5. A 049 ainda não está aplicada (nenhuma das colunas novas em contracts ou
     proposals, nenhuma close_contract em qualquer assinatura, nem a função
     ou o trigger de guarda).
Antes de gravar mede: contagem + md5 de contracts (sem term_months,
billing_interval_months, termination_notice_date e termination_reason, que a
049 cria) e de proposals (sem term_months e billing_interval_months), de
contract_installments e de contract_revenue_splits (linha inteira, ordenada
por id); quantos parcelados têm installments_count (contracts + proposals);
os privilégios (proacl) de generate e extend; md5 do corpo de close_deal,
set_contract_splits e is_master().
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.

Verificações esperadas na conexão nova: 33
  V1 term_months integer e nulo x 2 tabelas + V2 check > 0 x 2 tabelas
  + V1b billing_interval_months integer, not null, default 1 x 2 tabelas
  + V2b check in (1, 2, 3, 4, 6, 12) x 2 tabelas + V2c linhas existentes com intervalo 1 1
  + V1c termination_notice_date date e nulo 1 + V1d termination_reason text e nulo 1
  + V1e nenhum contrato com dados de encerramento 1
  + V3 preenchimento dos parcelados 1 + V3b nenhuma outra linha preenchida 1
  + V4 comentário de installments_count x 2 tabelas
  + V5 generate e extend com os blocos 049 1 + V5b privilégios de generate/extend iguais 1
  + V6 close_contract security definer e search_path vazio 1
  + V6b/c/d anon e PUBLIC sem EXECUTE, authenticated com 3
  + V6e só uma close_contract, a (uuid, date, text) 1
  + V7 trigger BEFORE UPDATE OF status 1 + V7b anon e authenticated sem EXECUTE na função de guarda 2
  = 26
  + D1 contracts fora das colunas novas 1 + D2 proposals fora das colunas novas 1
  + D3 contract_installments 1 + D4 contract_revenue_splits 1
  + D5 close_deal 1 + D6 set_contract_splits 1 + D7 is_master() 1
  = 7
"""
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "049_contract_term_months.sql"
REQUIRED_HOST = "us-west-2"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
OLD_SPLITS = "public.set_contract_splits(uuid, jsonb)"
NEW_SPLITS = "public.set_contract_splits(uuid, date, jsonb, boolean)"
CLOSE_FN = "public.close_contract(uuid, date, text)"
GUARD_FN = "public.fn_contracts_guard_close()"
NEW_COLUMNS = ["term_months", "billing_interval_months", "termination_notice_date", "termination_reason"]
SPLITS_SRC_SQL = "select prosrc from pg_proc where oid = to_regprocedure('public.set_contract_splits(uuid, date, jsonb, boolean)')"
GEN_EXT_ACL_SQL = ("select string_agg(p.proname || '=' || coalesce(p.proacl::text, ''), '|' order by p.proname) "
                   "from pg_proc p where p.pronamespace = 'public'::regnamespace "
                   "and p.proname in ('generate_contract_installments', 'extend_recurring_installments')")
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
SPLITS_MD5_SQL = f"select md5(pg_get_functiondef(to_regprocedure('{NEW_SPLITS}')))"
IS_MASTER_MD5_SQL = "select md5(pg_get_functiondef(to_regprocedure('public.is_master()')))"
# contracts e proposals sem as colunas novas da 049, para comparar antes e depois
TABLES = [("contracts", "public.contracts",
           "(to_jsonb(x) - 'term_months' - 'billing_interval_months' - 'termination_notice_date' "
           "- 'termination_reason')"),
          ("proposals", "public.proposals", "(to_jsonb(x) - 'term_months' - 'billing_interval_months')"),
          ("contract_installments", "public.contract_installments", "to_jsonb(x)"),
          ("contract_revenue_splits", "public.contract_revenue_splits", "to_jsonb(x)")]
PARCELADOS_SQL = ("select (select count(*) from public.contracts where payment_type = 'parcelado' "
                  "and installments_count is not null) + (select count(*) from public.proposals "
                  "where payment_type = 'parcelado' and installments_count is not null)")

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
    for key, table, expr in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.id), '')) as h "
            f"from {table} x")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
    out["splits"] = await c.fetchval(SPLITS_MD5_SQL)
    out["is_master"] = await c.fetchval(IS_MASTER_MD5_SQL)
    return out


async def column(c, table, col):
    row = await c.fetchrow("select data_type::text, is_nullable::text, column_default::text "
                           "from information_schema.columns where table_schema = 'public' "
                           "and table_name = $1 and column_name = $2", table, col)
    return tuple(row) if row else None


# ---------- travas + medição + aplicação ----------
async def apply(dsn, sql):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        num = int(await c.fetchval("show server_version_num"))
        print(f"server_version_num: {num}")
        if num < 150000:
            abort("Postgres anterior ao 15")
        if not await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                                "and table_name = 'contract_revenue_splits' and column_name = 'valid_from') "
                                "and to_regprocedure($1::text) is not null and to_regprocedure($2::text) is null",
                                NEW_SPLITS, OLD_SPLITS):
            abort("a 047 não está aplicada")
        if "exclusivo do master" not in (await c.fetchval(SPLITS_SRC_SQL) or ""):
            abort("a 048 não está aplicada (set_contract_splits sem a regra do master)")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name in ('contracts', 'proposals') and column_name = any($1::text[])) "
                            "or exists (select 1 from pg_proc where pronamespace = 'public'::regnamespace "
                            "and proname in ('close_contract', 'fn_contracts_guard_close')) "
                            "or exists (select 1 from pg_trigger where tgname = 'trg_contracts_guard_close')",
                            NEW_COLUMNS):
            abort("a 049 parece já aplicada (colunas novas, close_contract ou a guarda de encerramento existem)")

        before = await fingerprints(c)
        before["parcelados"] = await c.fetchval(PARCELADOS_SQL)
        before["genext_acl"] = await c.fetchval(GEN_EXT_ACL_SQL)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in TABLES)
              + f"; parcelados com installments_count: {before['parcelados']}"
              f"; close_deal md5 {before['close_deal'][:12]}…; set_contract_splits md5 {before['splits'][:12]}…; "
              f"is_master md5 {before['is_master'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n049 aplicada e COMMIT feito.\n")
        return before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify_structure(c, before):
    for t in ("contracts", "proposals"):
        got = await column(c, t, "term_months")
        record(f"V1 {t}.term_months: integer, aceita nulo", got is not None and got[:2] == ("integer", "YES"),
               f"veio {got!r}")
        await check(c, f"V2 {t}: check term_months > 0 existe",
                    "select count(*) from pg_constraint where conname = $1 and contype = 'c'", 1,
                    f"{t}_term_months_positive")
    for t in ("contracts", "proposals"):
        got = await column(c, t, "billing_interval_months")
        record(f"V1b {t}.billing_interval_months: integer, not null, default 1",
               got == ("integer", "NO", "1"), f"veio {got!r}")
        await check(c, f"V2b {t}: check billing_interval_months in (1, 2, 3, 4, 6, 12) existe",
                    "select count(*) from pg_constraint where conname = $1 and contype = 'c'", 1,
                    f"{t}_billing_interval_months_valid")
    await check(c, "V2c todas as linhas existentes ficaram com intervalo 1 (contracts + proposals)",
                "select (select count(*) from public.contracts where billing_interval_months <> 1) + "
                "(select count(*) from public.proposals where billing_interval_months <> 1)", 0)
    got = await column(c, "contracts", "termination_notice_date")
    record("V1c contracts.termination_notice_date: date, aceita nulo",
           got is not None and got[:2] == ("date", "YES"), f"veio {got!r}")
    got = await column(c, "contracts", "termination_reason")
    record("V1d contracts.termination_reason: text, aceita nulo",
           got is not None and got[:2] == ("text", "YES"), f"veio {got!r}")
    await check(c, "V1e nenhum contrato com dados de encerramento preenchidos",
                "select count(*) from public.contracts "
                "where termination_notice_date is not null or termination_reason is not null", 0)
    await check(c, "V3 parcelados com installments_count receberam term_months igual",
                "select (select count(*) from public.contracts where payment_type = 'parcelado' "
                "and installments_count is not null and term_months = installments_count) + "
                "(select count(*) from public.proposals where payment_type = 'parcelado' "
                "and installments_count is not null and term_months = installments_count)",
                before["parcelados"])
    await check(c, "V3b nenhum outro contrato ou proposta recebeu term_months",
                "select (select count(*) from public.contracts where term_months is not null and not "
                "(payment_type = 'parcelado' and installments_count is not null)) + "
                "(select count(*) from public.proposals where term_months is not null and not "
                "(payment_type = 'parcelado' and installments_count is not null))", 0)
    for t in ("contracts", "proposals"):
        await check(c, f"V4 {t}.installments_count comentado como substituído por term_months",
                    "select coalesce(col_description(($1::text)::regclass, a.attnum), '') "
                    "like 'Substituído por term_months%' from pg_attribute a "
                    "where a.attrelid = ($1::text)::regclass and a.attname = 'installments_count'",
                    True, f"public.{t}")
    await check(c, "V5 generate e extend com os blocos 049",
                "select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
                "and proname in ('generate_contract_installments', 'extend_recurring_installments') "
                "and prosrc like '%-- 049:%'", 2)
    record("V5b privilégios de generate/extend idênticos aos de antes",
           await c.fetchval(GEN_EXT_ACL_SQL) == before["genext_acl"])
    await check(c, "V6 close_contract: security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, CLOSE_FN)
    await check(c, "V6b anon sem EXECUTE em close_contract",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, CLOSE_FN)
    await check(c, "V6c PUBLIC sem EXECUTE em close_contract",
                "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                "where p.oid = to_regprocedure($1::text) and a.grantee = 0", 0, CLOSE_FN)
    await check(c, "V6d authenticated com EXECUTE em close_contract",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, CLOSE_FN)
    await check(c, "V6e só uma close_contract, a (uuid, date, text)",
                "select count(*) = 1 and bool_and(oid = to_regprocedure($1::text)) from pg_proc "
                "where proname = 'close_contract' and pronamespace = 'public'::regnamespace", True, CLOSE_FN)
    await check(c, "V7 trigger trg_contracts_guard_close é BEFORE UPDATE OF status",
                "select pg_get_triggerdef(oid) like '%BEFORE UPDATE OF status ON public.contracts%' "
                "from pg_trigger where tgname = 'trg_contracts_guard_close'", True)
    for role in ("anon", "authenticated"):
        await check(c, f"V7b {role} sem EXECUTE na função do trigger",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, GUARD_FN)


async def verify(dsn, before):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            await verify_structure(c, before)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            labels = {"contracts": "D1 contracts igual ao começo fora das colunas novas",
                      "proposals": "D2 proposals igual ao começo fora das colunas novas",
                      "contract_installments": "D3 contract_installments igual ao começo",
                      "contract_revenue_splits": "D4 contract_revenue_splits igual ao começo"}
            for key, _, _ in TABLES:
                record(f"{labels[key]} (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D5 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
            record("D6 set_contract_splits igual ao começo (md5)", after["splits"] == before["splits"])
            record("D7 is_master() igual ao começo (md5)", after["is_master"] == before["is_master"])
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
