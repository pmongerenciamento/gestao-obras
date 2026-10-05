"""Aplica a 048 em PRODUÇÃO com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_048_prod.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env com sa-east-1 e a ref de produção, sem a
     ref de staging (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 047 está aplicada (valid_from existe, só a assinatura nova de
     set_contract_splits existe).
  5. A 048 ainda não está aplicada (o corpo de set_contract_splits não tem a
     regra do master).
  6. public.is_master() existe (043).
  7. Exatamente 1 master em profiles, e é a conta do Diego (resolvida pelo
     e-mail, que não é impresso).
Antes de gravar mede: o corpo (prosrc) e os privilégios (proacl) de
set_contract_splits; contagem + md5 (linha inteira, ordenada por id) de
auth.users, profiles, teams, profile_modules, team_members, contracts,
contract_installments, contract_revenue_splits, bank_transactions e
service_types; o md5 do perfil + módulos do Diego; md5 do corpo do
close_deal, de generate/extend e de is_master(). Nenhuma contagem real está
escrita no código.
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.
Se o md5 de auth.users mudar, pode ser login real (last_sign_in_at): o script
avisa e mostra profiles e teams lado a lado para decisão humana.

Verificações esperadas na conexão nova: 23
  V1 regra do master no corpo 1 + V2 corpo igual ao da 047 tirando o bloco 1
  + V3 assinatura única 1 + V4 security definer e search_path vazio 1
  + V5 anon e PUBLIC sem EXECUTE, authenticated com 3 + V6 privilégios iguais aos de antes 1
  + D1 tabela inteira igual ao começo (10 tabelas) 10
  + D2 close_deal igual 1 + D3 generate/extend iguais 1 + D4 is_master() igual 1
  + D5 Diego igual 1 + D6 masters = 1 e é o Diego 1
"""
import asyncio
import re
import ssl
import sys
from pathlib import Path

import asyncpg

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env"
MIGRATION = ROOT / "migrations" / "048_split_retroactive_master_only.sql"
REQUIRED_HOST = "sa-east-1"
MASTER_EMAIL = "diego@pmongerenciamento.com.br"
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
TABLES = [("auth_users", "auth.users"),
          ("profiles", "public.profiles"),
          ("teams", "public.teams"),
          ("profile_modules", "public.profile_modules"),
          ("team_members", "public.team_members"),
          ("contracts", "public.contracts"),
          ("contract_installments", "public.contract_installments"),
          ("contract_revenue_splits", "public.contract_revenue_splits"),
          ("bank_transactions", "public.bank_transactions"),
          ("service_types", "public.service_types")]

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
                                "and table_name = 'contract_revenue_splits' and column_name = 'valid_from') "
                                "and to_regprocedure($1::text) is not null and to_regprocedure($2::text) is null",
                                NEW_SPLITS, OLD_SPLITS):
            abort("a 047 não está aplicada")
        row = await c.fetchrow(SPLITS_ROW_SQL)
        if "exclusivo do master" in row["prosrc"]:
            abort("a 048 parece já aplicada (set_contract_splits já tem a regra do master)")
        if not await c.fetchval("select to_regprocedure('public.is_master()') is not null"):
            abort("public.is_master() não existe (043)")

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
        before["splits_src"], before["splits_acl"] = row["prosrc"], row["acl"]
        before["diego"] = await diego_fp(c, diego)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _ in TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…; generate/extend md5 {before['genext'][:12]}…; "
              f"is_master md5 {before['is_master'][:12]}…; Diego md5 {before['diego'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n048 aplicada e COMMIT feito.\n")
        return diego, before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify(dsn, diego, before):
    c = await asyncpg.connect(dsn=dsn, ssl=ssl_ctx())
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
            for key, _ in TABLES:
                record(f"D1 {key}: tabela inteira igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D2 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
            record("D3 corpo de generate/extend igual ao começo (md5)", after["genext"] == before["genext"])
            record("D4 is_master() igual ao começo (md5)", after["is_master"] == before["is_master"])
            record("D5 perfil e módulos do Diego iguais ao começo (md5)", await diego_fp(c, diego) == before["diego"])
            m = await master_ids(c)
            record("D6 masters = 1 e é o Diego", m == [diego], f"{len(m)} master(s)")

            if after["auth_users"] != before["auth_users"]:
                print("\nAVISO: auth.users mudou. Pode ser login real durante a aplicação "
                      "(last_sign_in_at/updated_at), não necessariamente a 048. Para decidir:")
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
