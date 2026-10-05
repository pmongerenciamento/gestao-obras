"""Aplica a 047 em PRODUÇÃO com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_047_prod.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env com sa-east-1 e a ref de produção, sem a
     ref de staging (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 046 está aplicada (contracts.first_due_date e generate_contract_installments).
  5. A 047 ainda não está aplicada (contract_revenue_splits.valid_from não existe).
  6. contract_revenue_splits vazia (a própria 047 também aborta se não estiver).
  7. Exatamente 1 master em profiles, e é a conta do Diego (resolvida pelo
     e-mail, que não é impresso).
Antes de gravar mede contagem + md5 (linha inteira, ordenada por id) de
auth.users, profiles, teams, profile_modules, team_members, contracts,
contract_installments, contract_revenue_splits (sem valid_from),
bank_transactions e service_types, o md5 do perfil + módulos do Diego e o md5
do corpo do close_deal. Nenhuma contagem real está escrita no código.
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.
Se o md5 de auth.users mudar, pode ser login real (last_sign_in_at): o script
avisa e mostra profiles e teams lado a lado para decisão humana.

Verificações esperadas na conexão nova: 25
  V1 valid_from date not null 1 + V2 check de dia 1 1 + V3 unicidade nova 1
  + V4 assinatura nova existe 1 + V5 assinatura antiga não existe 1
  + V6 nova set_contract_splits: anon e PUBLIC sem EXECUTE, authenticated com 3
  + V7 search_path vazio nas 4 funções da 047 4
  + D1 tabela inteira igual ao começo (10 tabelas) 10
  + D2 corpo do close_deal igual 1 + D3 Diego igual 1 + D4 masters = 1 e é o Diego 1
"""
import asyncio
import re
import ssl
import sys
from pathlib import Path

import asyncpg

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env"
MIGRATION = ROOT / "migrations" / "047_split_effective_dating.sql"
REQUIRED_HOST = "sa-east-1"
MASTER_EMAIL = "diego@pmongerenciamento.com.br"
# (chave, tabela, expressão json da linha). contract_revenue_splits sem a
# coluna nova da 047, para comparar antes (sem coluna) e depois (com).
REAL_TABLES = [("auth_users", "auth.users", "to_jsonb(x)"),
               ("profiles", "public.profiles", "to_jsonb(x)"),
               ("teams", "public.teams", "to_jsonb(x)"),
               ("profile_modules", "public.profile_modules", "to_jsonb(x)"),
               ("team_members", "public.team_members", "to_jsonb(x)"),
               ("contracts", "public.contracts", "to_jsonb(x)"),
               ("contract_installments", "public.contract_installments", "to_jsonb(x)"),
               ("contract_revenue_splits", "public.contract_revenue_splits", "(to_jsonb(x) - 'valid_from')"),
               ("bank_transactions", "public.bank_transactions", "to_jsonb(x)"),
               ("service_types", "public.service_types", "to_jsonb(x)")]
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
OLD_SPLITS = "public.set_contract_splits(uuid, jsonb)"
NEW_SPLITS = "public.set_contract_splits(uuid, date, jsonb, boolean)"
FUNCS_047 = ["public.fn_contract_revenue_splits_sum_100()",
             NEW_SPLITS,
             "public.generate_contract_installments(uuid, text, text)",
             "public.extend_recurring_installments(uuid)"]
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")

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
    abort("DATABASE_URL não encontrado em backend/.env")


def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


async def check_row(c, name, sql, expected, *args):
    row = await c.fetchrow(sql, *args)
    got = tuple(row) if row is not None else None
    record(name, got == tuple(expected), f"esperado {tuple(expected)!r}, veio {got!r}")


def fmt(fp):
    return f"{fp[0]} (md5 {fp[1][:12]}…)"


# ---------- medições ----------
async def fingerprints(c):
    out = {}
    for key, table, expr in REAL_TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.id), '')) as h "
            f"from {table} x")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
    return out


async def diego_fp(c, diego):
    return await c.fetchval(
        "select md5(coalesce((select row_to_json(p)::text from public.profiles p where p.id = $1), '') || '|' || "
        "coalesce((select string_agg(module, ',' order by module) from public.profile_modules "
        "where profile_id = $1), ''))", diego)


async def master_ids(c):
    return [r["id"] for r in await c.fetch("select id from public.profiles where system_role = 'master'")]


# ---------- travas + medição + aplicação ----------
async def apply(dsn, sql):
    c = await asyncpg.connect(dsn=dsn, ssl=ssl_ctx())
    try:
        num = int(await c.fetchval("show server_version_num"))
        print(f"server_version_num: {num}")
        if num < 150000:
            abort("Postgres anterior ao 15")
        if not await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                                "and table_name = 'contracts' and column_name = 'first_due_date') "
                                "and to_regprocedure('public.generate_contract_installments(uuid, text, text)') "
                                "is not null"):
            abort("a 046 não está aplicada")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'contract_revenue_splits' and column_name = 'valid_from')"):
            abort("contract_revenue_splits.valid_from já existe: a 047 parece aplicada")
        n_splits = await c.fetchval("select count(*) from public.contract_revenue_splits")
        print(f"contract_revenue_splits: {n_splits} linha(s)")
        if n_splits:
            abort("contract_revenue_splits não está vazia: a 047 exige a tabela vazia")

        rows = await c.fetch("select id from auth.users where lower(email) = lower($1::text)", MASTER_EMAIL)
        if len(rows) != 1:
            abort(f"esperada 1 conta com o e-mail do Diego, achou {len(rows)}")
        diego = rows[0]["id"]
        m = await master_ids(c)
        print(f"masters em profiles: {len(m)}")
        if len(m) != 1:
            abort(f"esperado exatamente 1 master, achou {len(m)}")
        if m[0] != diego:
            abort("o master existente não é a conta do Diego (resolvida pelo e-mail)")
        print("master existente = conta do Diego (resolvida pelo e-mail)")

        before = await fingerprints(c)
        before["diego"] = await diego_fp(c, diego)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in REAL_TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…; Diego md5 {before['diego'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n047 aplicada e COMMIT feito.\n")
        return diego, before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify(dsn, diego, before):
    c = await asyncpg.connect(dsn=dsn, ssl=ssl_ctx())
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")

            await check_row(c, "V1 contract_revenue_splits.valid_from: date e not null",
                            "select data_type::text, is_nullable::text from information_schema.columns "
                            "where table_schema = 'public' and table_name = 'contract_revenue_splits' "
                            "and column_name = 'valid_from'", ("date", "NO"))
            await check(c, "V2 check de dia 1 (contract_revenue_splits_valid_from_day1)",
                        "select count(*) from pg_constraint where conname = 'contract_revenue_splits_valid_from_day1' "
                        "and contype = 'c'", 1)
            await check(c, "V3 unicidade nova com valid_from (nulls not distinct)",
                        "select pg_get_constraintdef(oid) like 'UNIQUE NULLS NOT DISTINCT (contract_id, valid_from, "
                        "share_kind, team_id, scope)%' from pg_constraint where conname = 'contract_revenue_splits_unique'",
                        True)
            await check(c, "V4 set_contract_splits(uuid, date, jsonb, boolean) existe",
                        "select to_regprocedure($1::text) is not null", True, NEW_SPLITS)
            await check(c, "V5 set_contract_splits(uuid, jsonb) não existe mais",
                        "select to_regprocedure($1::text) is null", True, OLD_SPLITS)
            await check(c, "V6 anon sem EXECUTE na nova set_contract_splits",
                        "select has_function_privilege('anon'::name, $1::text, 'execute')", False, NEW_SPLITS)
            await check(c, "V6b PUBLIC sem EXECUTE na nova set_contract_splits",
                        "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                        "where p.oid = ($1::text)::regprocedure and a.grantee = 0", 0, NEW_SPLITS)
            await check(c, "V6c authenticated com EXECUTE na nova set_contract_splits",
                        "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, NEW_SPLITS)
            for f in FUNCS_047:
                await check(c, f"V7 search_path vazio em {f.split('.')[1].split('(')[0]}",
                            "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                            "from pg_proc where oid = ($1::text)::regprocedure", True, f)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for key, _, _ in REAL_TABLES:
                record(f"D1 {key}: tabela inteira igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D2 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"],
                   f"antes {before['close_deal'][:12]}…, depois {after['close_deal'][:12]}…")
            record("D3 perfil e módulos do Diego iguais ao começo (md5)", await diego_fp(c, diego) == before["diego"])
            m = await master_ids(c)
            record("D4 masters = 1 e é o Diego", m == [diego], f"{len(m)} master(s)")

            if after["auth_users"] != before["auth_users"]:
                print("\nAVISO: auth.users mudou. Pode ser login real durante a aplicação "
                      "(last_sign_in_at/updated_at), não necessariamente a 047. Para decidir:")
                for key in ("profiles", "teams"):
                    print(f"  {key}: antes {fmt(before[key])}, depois {fmt(after[key])}, "
                          f"igual: {after[key] == before[key]}")
                print(f"  auth_users: antes {fmt(before['auth_users'])}, depois {fmt(after['auth_users'])}, "
                      f"contagem igual: {after['auth_users'][0] == before['auth_users'][0]}")
    finally:
        await c.close()


async def main():
    dsn = load_dsn()
    if REQUIRED_HOST not in dsn:
        abort(f"DATABASE_URL não contém {REQUIRED_HOST}: não é produção")
    if PROD_REF not in dsn:
        abort("DATABASE_URL não contém a ref de produção")
    if STAGING_REF in dsn:
        abort("DATABASE_URL contém a ref de STAGING")

    sql = MIGRATION.read_text(encoding="utf-8")
    if re.search(r"^\s*(begin|commit|rollback)\s*;", sql, re.I | re.M):
        abort("a migration tem begin/commit/rollback no nível de topo")

    diego, before = await apply(dsn, sql)
    await verify(dsn, diego, before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
