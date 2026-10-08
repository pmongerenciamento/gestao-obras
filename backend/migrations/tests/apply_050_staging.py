"""Aplica a 050 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_050_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 049 está aplicada (contracts.term_months e close_contract(uuid, date,
     text) existem).
  5. A 050 ainda não está aplicada (nenhuma das 5 tabelas novas existe).
Antes de gravar mede: contagem + md5 (linha inteira, ordenada pela chave) de
contracts, proposals, billing_entities, clients, service_types, projects,
profiles, profile_modules, contract_installments e contract_revenue_splits, e
de resources e permissions fora das 5 chaves novas; md5 do corpo do close_deal.
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.

Verificações esperadas na conexão nova: 49
  V1 tabela existe + V2 RLS ligada + V3 anon sem nenhum privilégio
  + V4 DELETE para authenticated só em company_tax_regimes          x 5 tabelas = 20
  + V5 função existe + V6 search_path vazio
  + V7 sem EXECUTE para anon, PUBLIC e authenticated                 x 3 funções = 9
  + V8 seed do regime (1 linha, simples desde 2026-01-01) 1
  + V9 seeds da taxa (2026-06-01 e 2026-07-01 com 0,167) 1
  + V10 os 5 recursos 1 + V11 as 9 permissões como conjunto exato 1
  + V12 índice único de e-mail x 2 índices 2
  + V13 gatilho trg_company_tax_regimes_guard (BEFORE INSERT/UPDATE/DELETE, por linha, ligado) 1
  = 36
  + D1 tabela existente igual ao começo (contagem + md5)            x 12 tabelas = 12
  + D2 corpo do close_deal igual ao começo (md5) 1
  = 13
"""
import asyncio
import datetime
import re
import sys
from decimal import Decimal
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "050_billing_registry.sql"
REQUIRED_HOST = "us-west-2"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
NEW_TABLES = ["taxpayer_profiles", "billing_contacts", "contract_fiscal_settings",
              "company_tax_regimes", "dre_tax_rates"]
NEW_FUNCS = ["public.fn_set_created_by()", "public.fn_tax_regime_locked_count(date, date)",
             "public.fn_company_tax_regimes_guard()"]
GUARD_FN = "public.fn_company_tax_regimes_guard()"
EMAIL_INDEXES = ["uq_billing_contacts_billing_entity_email", "uq_billing_contacts_contract_email"]
EXPECTED_PERMS = {
    ("financeiro", "taxpayer_profiles", True, True), ("crm", "taxpayer_profiles", True, False),
    ("financeiro", "billing_contacts", True, True), ("crm", "billing_contacts", True, False),
    ("financeiro", "contract_fiscal_settings", True, True), ("crm", "contract_fiscal_settings", True, False),
    ("financeiro", "company_tax_regimes", True, False), ("crm", "company_tax_regimes", True, False),
    ("financeiro", "dre_tax_rates", True, True),
}
NEW_KEYS_SQL = "array[" + ", ".join(f"'{t}'" for t in NEW_TABLES) + "]"
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
# (chave, origem com alias x, coluna de ordenação)
TABLES = [("contracts", "public.contracts x", "x.id"),
          ("proposals", "public.proposals x", "x.id"),
          ("billing_entities", "public.billing_entities x", "x.id"),
          ("clients", "public.clients x", "x.id"),
          ("service_types", "public.service_types x", "x.id"),
          ("projects", "public.projects x", "x.id"),
          ("profiles", "public.profiles x", "x.id"),
          ("profile_modules", "public.profile_modules x", "x.id"),
          ("contract_installments", "public.contract_installments x", "x.id"),
          ("contract_revenue_splits", "public.contract_revenue_splits x", "x.id"),
          ("resources", f"public.resources x where x.key <> all({NEW_KEYS_SQL})", "x.key"),
          ("permissions", f"public.permissions x where x.resource_key <> all({NEW_KEYS_SQL})", "x.id")]

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
    for key, source, order in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg(to_jsonb(x)::text, ',' order by {order}), '')) as h "
            f"from {source}")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
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
                                "and table_name = 'contracts' and column_name = 'term_months') "
                                "and to_regprocedure('public.close_contract(uuid, date, text)') is not null"):
            abort("a 049 não está aplicada (contracts.term_months ou close_contract ausente)")
        present = [t for t in NEW_TABLES
                   if await c.fetchval("select to_regclass($1::text) is not null", f"public.{t}")]
        if present:
            abort(f"a 050 parece já aplicada ({', '.join(present)} existe)")

        before = await fingerprints(c)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n050 aplicada e COMMIT feito.\n")
        return before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify_structure(c):
    for t in NEW_TABLES:
        rel = f"public.{t}"
        await check(c, f"V1 {t} existe", "select to_regclass($1::text) is not null", True, rel)
        await check(c, f"V2 {t}: RLS ligada",
                    "select relrowsecurity from pg_class where oid = ($1::text)::regclass", True, rel)
        await check(c, f"V3 {t}: anon sem nenhum privilégio",
                    "select bool_or(has_table_privilege('anon'::name, $1::text, p)) from unnest(array['SELECT', "
                    "'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p", False, rel)
        with_delete = t == "company_tax_regimes"
        await check(c, f"V4 {t}: authenticated {'com' if with_delete else 'sem'} DELETE",
                    "select has_table_privilege('authenticated'::name, $1::text, 'DELETE')", with_delete, rel)
    for fn in NEW_FUNCS:
        await check(c, f"V5 {fn} existe", "select to_regprocedure($1::text) is not null", True, fn)
        await check(c, f"V6 {fn}: search_path vazio",
                    "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                    "from pg_proc where oid = to_regprocedure($1::text)", True, fn)
        await check(c, f"V7 {fn}: sem EXECUTE para anon, PUBLIC e authenticated",
                    "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                    "and not has_function_privilege('authenticated'::name, $1::text, 'execute') "
                    "and not exists (select 1 from pg_proc p, aclexplode(p.proacl) a "
                    "where p.oid = to_regprocedure($1::text) and a.grantee = 0 and a.privilege_type = 'EXECUTE')",
                    True, fn)
    got = [(r["valid_from"], r["regime"]) for r in
           await c.fetch("select valid_from, regime from public.company_tax_regimes order by valid_from")]
    record("V8 company_tax_regimes: uma linha, 'simples' desde 2026-01-01",
           got == [(datetime.date(2026, 1, 1), "simples")], str(got))
    got = [(r["month"], r["rate"]) for r in await c.fetch("select month, rate from public.dre_tax_rates order by month")]
    record("V9 dre_tax_rates: 2026-06-01 e 2026-07-01 com 0,167",
           got == [(datetime.date(2026, 6, 1), Decimal("0.167")), (datetime.date(2026, 7, 1), Decimal("0.167"))],
           str(got))
    await check(c, "V10 catálogo: os 5 recursos novos",
                "select count(*) from public.resources where key = any($1::text[])", 5, NEW_TABLES)
    perms = {(r["module_code"], r["resource_key"], r["can_read"], r["can_write"]) for r in await c.fetch(
        "select module_code, resource_key, can_read, can_write from public.permissions "
        "where resource_key = any($1::text[])", NEW_TABLES)}
    record("V11 catálogo: exatamente as 9 permissões combinadas", perms == EXPECTED_PERMS, str(sorted(perms)))
    for idx in EMAIL_INDEXES:
        await check(c, f"V12 {idx}: único, parcial e por lower(email)",
                    "select indexdef like 'CREATE UNIQUE INDEX %lower(email)%WHERE%' from pg_indexes "
                    "where schemaname = 'public' and tablename = 'billing_contacts' and indexname = $1", True, idx)
    # tgtype 31 = ROW (1) + BEFORE (2) + INSERT (4) + DELETE (8) + UPDATE (16); tgenabled 'O' = ligado
    await check(c, "V13 gatilho trg_company_tax_regimes_guard: BEFORE INSERT/UPDATE/DELETE, por linha, ligado",
                "select count(*) from pg_trigger where tgname = 'trg_company_tax_regimes_guard' "
                "and tgrelid = 'public.company_tax_regimes'::regclass and tgtype = 31 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text)", 1, GUARD_FN)


async def verify(dsn, before):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            await verify_structure(c)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for key, _, _ in TABLES:
                record(f"D1 {key}: igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D2 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
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
