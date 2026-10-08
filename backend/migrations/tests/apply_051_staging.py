"""Aplica a 051 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_051_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 050 está aplicada (taxpayer_profiles existe).
  5. A 051 ainda não está aplicada (contracts.billing_entity_id ausente e
     contract_billing_entity_id inexistente).
Antes de gravar mede: contagem + md5 (linha inteira, ordenada por id) de
contracts (sem billing_entity_id: to_jsonb(x) - 'billing_entity_id'),
billing_entities, projects, clients, proposals, contract_installments e
contract_revenue_splits; md5 do corpo do close_deal e do close_contract; e os
gatilhos de contracts que já existem (nome e se estão ligados).
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.

Verificações esperadas na conexão nova: 23
  V1 coluna uuid, nula, sem padrão 1 + V2 FK sem cascade 1 + V3 índice parcial 1
  + V4 função existe com search_path vazio x 3 funções 3
  + V5 EXECUTE: contract_billing_entity_id só para authenticated (sem anon e
       PUBLIC); funções de gatilho sem anon, PUBLIC e authenticated x 3 funções 3
  + V6 gatilho novo ligado, do tipo e com a função certos x 2 gatilhos 2
  + V7 gatilhos que já existiam em contracts continuam todos ligados, e os
       únicos a mais são os 2 novos 1
  + V8 trg_contracts_guard_close (049) existe e está ligado 1
  + V9 nenhum contrato existente com billing_entity_id preenchido 1
  = 14
  + D1 tabela igual ao começo (contagem + md5) x 7 tabelas 7
  + D2 corpo do close_deal igual ao começo (md5) 1
  + D3 corpo do close_contract igual ao começo (md5) 1
  = 9
"""
import asyncio
import re
import ssl
import sys
from pathlib import Path

import asyncpg

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "051_contract_billing_entity.sql"
REQUIRED_HOST = "us-west-2"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
BE_FN = "public.contract_billing_entity_id(uuid)"
TRIGGER_FUNCS = ["public.fn_contracts_guard_insert()", "public.fn_contracts_guard_billing_entity()"]
# (nome, função, tgtype): 7 = ROW + BEFORE + INSERT; 23 = ROW + BEFORE + INSERT + UPDATE
NEW_TRIGGERS = [("trg_contracts_guard_insert", "public.fn_contracts_guard_insert()", 7),
                ("trg_contracts_guard_billing_entity", "public.fn_contracts_guard_billing_entity()", 23)]
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
CLOSE_CONTRACT_MD5_SQL = "select md5(pg_get_functiondef(to_regprocedure('public.close_contract(uuid, date, text)')))"
CONTRACT_TRIGGERS_SQL = ("select tgname::text as name, tgenabled::text as enabled from pg_trigger "
                         "where tgrelid = 'public.contracts'::regclass and not tgisinternal order by tgname")
# (chave, origem com alias x, expressão da linha)
TABLES = [("contracts", "public.contracts x", "(to_jsonb(x) - 'billing_entity_id')"),
          ("billing_entities", "public.billing_entities x", "to_jsonb(x)"),
          ("projects", "public.projects x", "to_jsonb(x)"),
          ("clients", "public.clients x", "to_jsonb(x)"),
          ("proposals", "public.proposals x", "to_jsonb(x)"),
          ("contract_installments", "public.contract_installments x", "to_jsonb(x)"),
          ("contract_revenue_splits", "public.contract_revenue_splits x", "to_jsonb(x)")]

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


async def fingerprints(c):
    out = {}
    for key, source, expr in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.id), '')) as h "
            f"from {source}")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
    out["close_contract"] = await c.fetchval(CLOSE_CONTRACT_MD5_SQL)
    return out


async def contract_triggers(c):
    return {r["name"]: r["enabled"] for r in await c.fetch(CONTRACT_TRIGGERS_SQL)}


# ---------- travas + medição + aplicação ----------
async def apply(dsn, sql):
    c = await asyncpg.connect(dsn=dsn, ssl=ssl_ctx())
    try:
        num = int(await c.fetchval("show server_version_num"))
        print(f"server_version_num: {num}")
        if num < 150000:
            abort("Postgres anterior ao 15")
        if not await c.fetchval("select to_regclass('public.taxpayer_profiles') is not null"):
            abort("a 050 não está aplicada (taxpayer_profiles ausente)")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'contracts' and column_name = 'billing_entity_id') "
                            "or to_regprocedure($1::text) is not null", BE_FN):
            abort("a 051 parece já aplicada (contracts.billing_entity_id ou contract_billing_entity_id existe)")

        before = await fingerprints(c)
        before["triggers"] = await contract_triggers(c)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…; close_contract md5 {before['close_contract'][:12]}…"
              f"; gatilhos de contracts: {sorted(before['triggers'])}")

        async with c.transaction():
            await c.execute(sql)
        print("\n051 aplicada e COMMIT feito.\n")
        return before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify_structure(c, before):
    got = await c.fetchrow("select data_type::text, is_nullable::text, column_default::text "
                           "from information_schema.columns where table_schema = 'public' "
                           "and table_name = 'contracts' and column_name = 'billing_entity_id'")
    got = tuple(got) if got else None
    record("V1 contracts.billing_entity_id: uuid, aceita nulo, sem padrão", got == ("uuid", "YES", None), f"veio {got!r}")
    await check(c, "V2 FK para billing_entities(id) sem cascade (on delete e on update no action)",
                "select count(*) from pg_constraint where conrelid = 'public.contracts'::regclass and contype = 'f' "
                "and confrelid = 'public.billing_entities'::regclass and confdeltype = 'a' and confupdtype = 'a' "
                "and conkey = array[(select attnum from pg_attribute where attrelid = 'public.contracts'::regclass "
                "and attname = 'billing_entity_id')]::int2[]", 1)
    await check(c, "V3 índice parcial idx_contracts_billing_entity onde não é nulo",
                "select indexdef like '%(billing_entity_id) WHERE (billing_entity_id IS NOT NULL)%' from pg_indexes "
                "where schemaname = 'public' and indexname = 'idx_contracts_billing_entity'", True)
    for fn in [BE_FN] + TRIGGER_FUNCS:
        await check(c, f"V4 {fn} existe com search_path vazio",
                    "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                    "from pg_proc where oid = to_regprocedure($1::text)", True, fn)
    no_public = ("not exists (select 1 from pg_proc p, aclexplode(p.proacl) a where p.oid = to_regprocedure($1::text) "
                 "and a.grantee = 0 and a.privilege_type = 'EXECUTE')")
    await check(c, f"V5 {BE_FN}: EXECUTE só para authenticated (sem anon e PUBLIC)",
                "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                f"and has_function_privilege('authenticated'::name, $1::text, 'execute') and {no_public}", True, BE_FN)
    for fn in TRIGGER_FUNCS:
        await check(c, f"V5 {fn}: sem EXECUTE para anon, PUBLIC e authenticated",
                    "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                    f"and not has_function_privilege('authenticated'::name, $1::text, 'execute') and {no_public}",
                    True, fn)
    for name, fn, tgtype in NEW_TRIGGERS:
        await check(c, f"V6 {name}: ligado, tipo {tgtype} e função certa",
                    "select count(*) from pg_trigger where tgname = $1 and tgrelid = 'public.contracts'::regclass "
                    "and tgtype = $2 and tgenabled = 'O' and tgfoid = to_regprocedure($3::text)", 1, name, tgtype, fn)
    after = await contract_triggers(c)
    kept = all(after.get(n) == "O" for n in before["triggers"])
    extra = sorted(set(after) - set(before["triggers"]))
    record("V7 gatilhos que já existiam em contracts continuam ligados, e só os 2 novos foram acrescentados",
           kept and extra == sorted(n for n, _, _ in NEW_TRIGGERS),
           f"antes {sorted(before['triggers'])}, depois {sorted(after)}")
    await check(c, "V8 trg_contracts_guard_close (049) existe e está ligado",
                "select count(*) from pg_trigger where tgname = 'trg_contracts_guard_close' "
                "and tgrelid = 'public.contracts'::regclass and tgenabled = 'O'", 1)
    await check(c, "V9 nenhum contrato existente com billing_entity_id preenchido",
                "select count(*) from public.contracts where billing_entity_id is not null", 0)


async def verify(dsn, before):
    c = await asyncpg.connect(dsn=dsn, ssl=ssl_ctx())
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            await verify_structure(c, before)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for key, _, _ in TABLES:
                record(f"D1 {key}: igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D2 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
            record("D3 corpo do close_contract igual ao começo (md5)",
                   after["close_contract"] == before["close_contract"])
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
