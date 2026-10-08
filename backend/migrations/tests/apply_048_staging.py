"""Aplica a 048 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_048_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 047 está aplicada (valid_from existe, só a assinatura nova de
     set_contract_splits existe).
  5. A 048 ainda não está aplicada (o corpo de set_contract_splits não tem a
     regra do master).
  6. public.is_master() existe (043).
Antes de gravar mede: o corpo (prosrc) e os privilégios (proacl) de
set_contract_splits; contagem + md5 de contract_revenue_splits e de
contract_installments (linha inteira, ordenada por id); md5 do corpo do
close_deal, de generate/extend e de is_master().
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.

Verificações esperadas na conexão nova: 13
  V1 regra do master no corpo 1 + V2 corpo igual ao da 047 tirando o bloco 1
  + V3 assinatura única 1 + V4 security definer e search_path vazio 1
  + V5 anon e PUBLIC sem EXECUTE, authenticated com 3 + V6 privilégios iguais aos de antes 1
  + D1 contract_revenue_splits igual 1 + D2 contract_installments igual 1
  + D3 close_deal igual 1 + D4 generate/extend iguais 1 + D5 is_master() igual 1
"""
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "048_split_retroactive_master_only.sql"
REQUIRED_HOST = "us-west-2"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
OLD_SPLITS = "public.set_contract_splits(uuid, jsonb)"
NEW_SPLITS = "public.set_contract_splits(uuid, date, jsonb, boolean)"
SPLITS_ROW_SQL = ("select prosrc, coalesce(proacl::text, '') as acl from pg_proc "
                  "where oid = to_regprocedure('public.set_contract_splits(uuid, date, jsonb, boolean)')")
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
GEN_EXT_MD5_SQL = ("select md5(string_agg(pg_get_functiondef(p.oid), '|' order by p.proname)) from pg_proc p "
                   "where p.pronamespace = 'public'::regnamespace "
                   "and p.proname in ('generate_contract_installments', 'extend_recurring_installments')")
IS_MASTER_MD5_SQL = "select md5(pg_get_functiondef(to_regprocedure('public.is_master()')))"
TABLES = [("contract_revenue_splits", "public.contract_revenue_splits"),
          ("contract_installments", "public.contract_installments")]

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


def nonblank(src):
    return "\n".join(l for l in src.splitlines() if l.strip())


def strip048(src):
    out, skip = [], False
    for line in src.splitlines():
        if "-- 048:" in line:
            skip = True
            continue
        if skip:
            if line.strip() == "end if;":
                skip = False
            continue
        out.append(line)
    return nonblank("\n".join(out))


async def fingerprints(c):
    out = {}
    for key, table in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg(to_jsonb(x)::text, ',' order by x.id), '')) as h "
            f"from {table} x")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
    out["genext"] = await c.fetchval(GEN_EXT_MD5_SQL)
    out["is_master"] = await c.fetchval(IS_MASTER_MD5_SQL)
    return out


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
        row = await c.fetchrow(SPLITS_ROW_SQL)
        if "exclusivo do master" in row["prosrc"]:
            abort("a 048 parece já aplicada (set_contract_splits já tem a regra do master)")
        if not await c.fetchval("select to_regprocedure('public.is_master()') is not null"):
            abort("public.is_master() não existe (043)")

        before = await fingerprints(c)
        before["splits_src"], before["splits_acl"] = row["prosrc"], row["acl"]
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _ in TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…; generate/extend md5 {before['genext'][:12]}…; "
              f"is_master md5 {before['is_master'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n048 aplicada e COMMIT feito.\n")
        return before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify(dsn, before):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            row = await c.fetchrow(SPLITS_ROW_SQL)
            record("V1 set_contract_splits tem a regra do master (bloco 048)",
                   "-- 048:" in row["prosrc"] and "exclusivo do master" in row["prosrc"])
            record("V2 corpo igual ao da 047 tirando o bloco 048",
                   strip048(row["prosrc"]) == nonblank(before["splits_src"]))
            await check(c, "V3 assinatura única: set_contract_splits(uuid, date, jsonb, boolean)",
                        "select count(*) = 1 and bool_and(oid = to_regprocedure($1::text)) from pg_proc "
                        "where proname = 'set_contract_splits' and pronamespace = 'public'::regnamespace",
                        True, NEW_SPLITS)
            await check(c, "V4 security definer e search_path vazio",
                        "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                        "from pg_proc where oid = to_regprocedure($1::text)", True, NEW_SPLITS)
            await check(c, "V5 anon sem EXECUTE",
                        "select has_function_privilege('anon'::name, $1::text, 'execute')", False, NEW_SPLITS)
            await check(c, "V5b PUBLIC sem EXECUTE",
                        "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                        "where p.oid = to_regprocedure($1::text) and a.grantee = 0", 0, NEW_SPLITS)
            await check(c, "V5c authenticated com EXECUTE",
                        "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, NEW_SPLITS)
            record("V6 privilégios (proacl) idênticos aos de antes da 048", row["acl"] == before["splits_acl"])

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for i, (key, _) in enumerate(TABLES, start=1):
                record(f"D{i} {key} igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D3 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
            record("D4 corpo de generate/extend igual ao começo (md5)", after["genext"] == before["genext"])
            record("D5 is_master() igual ao começo (md5)", after["is_master"] == before["is_master"])
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
