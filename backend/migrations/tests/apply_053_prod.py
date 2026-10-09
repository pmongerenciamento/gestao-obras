"""Aplica a 053 em PRODUÇÃO com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_053_prod.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env com sa-east-1 e a ref de produção, sem a
     ref de staging (antes de conectar).
  2. MASTER_EMAIL presente em backend/.env (antes de conectar). O e-mail não
     fica no código e não é impresso.
  3. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  4. server_version_num >= 150000.
  5. A 052 está aplicada (reimbursement_items.receipt_path e
     fn_reimbursement_items_validate_total existem).
  6. A 053 ainda não está aplicada (approved_amount ausente, função de guarda
     e policy reimbursement_items_approve_amount inexistentes).
  7. Exatamente 1 master em profiles, e é a conta do Diego (resolvida pelo
     MASTER_EMAIL).
Antes de gravar mede: contagem + md5 (linha inteira, ordenada pela chave) das
26 tabelas reais do test_053_prod.py (reimbursement_items sem approved_amount
e approval_note; allocation_rules e allocation_rule_splits inteiros); o md5
do perfil + módulos do Diego; o md5 do corpo do close_deal; as policies de
reimbursement_items e reimbursement_reports (md5); e os gatilhos que já
existem nas duas tabelas (nome e se estão ligados).
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.
Se o md5 de auth.users mudar, pode ser login real (last_sign_in_at): o script
avisa e mostra profiles e teams lado a lado para decisão humana.
Os testes funcionais não se repetem aqui: test_053_prod.py passou 127/127
dentro de transação desfeita. Aqui só estrutura e dados; as consultas de
estrutura são as mesmas do apply_053_staging.py.

Verificações esperadas na conexão nova: 39
  V1 approved_amount: numeric, nula, sem padrão 1
  + V2 approval_note: text, nula, sem padrão 1
  + V3 check reimbursement_items_approved_amount_nonneg 1
  + V4 gatilho de guarda: tipo 23 (BEFORE INSERT OR UPDATE, sem UPDATE OF),
       ligado, função certa 1
  + V5 função de guarda: security definer e search_path vazio 1
  + V6 função de guarda sem EXECUTE para anon, PUBLIC e authenticated 1
  + V7 policy reimbursement_items_approve_amount: UPDATE, is_master,
       'enviado', profile_id <> auth.uid() 1
  + V8 as demais policies de itens e relatórios iguais às de antes 1
  + V9 gatilhos que já existiam continuam ligados e só o novo foi acrescentado 1
  + V10 nenhum item existente com approved_amount ou approval_note preenchido 1
  = 10
  + D1 tabela real igual ao começo (contagem + md5) x 26 tabelas 26
  + D2 corpo do close_deal igual 1 + D3 perfil e módulos do Diego iguais 1
  + D4 masters = 1 e é o Diego 1
  = 10 + 26 + 3 = 39
"""
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env"
MIGRATION = ROOT / "migrations" / "053_reimbursement_approved_amount.sql"
REQUIRED_HOST = "sa-east-1"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
GUARD_FN = "public.fn_reimbursement_items_guard_approved_amount()"
NEW_POLICY = "reimbursement_items_approve_amount"
NEW_TRIGGER = "reimbursement_items.trg_reimbursement_items_guard_approved_amount"
CHECK_NAME = "reimbursement_items_approved_amount_nonneg"
POLICIES_SQL = ("select md5(coalesce(string_agg(tablename::text || ':' || policyname::text || ':' || cmd::text || ':' "
                "|| coalesce(qual, '') || ':' || coalesce(with_check, ''), '|' order by tablename, policyname), '')) "
                "from pg_policies where schemaname = 'public' "
                "and tablename in ('reimbursement_items', 'reimbursement_reports') and policyname <> $1::text")
TRIGGERS_SQL = ("select tgrelid::regclass::text || '.' || tgname::text as name, tgenabled::text as enabled "
                "from pg_trigger where tgrelid in ('public.reimbursement_items'::regclass, "
                "'public.reimbursement_reports'::regclass) and not tgisinternal order by 1")
COL_SQL = ("select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
           "where table_schema = 'public' and table_name = 'reimbursement_items' and column_name = $1::text")
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
# (chave, origem com alias x, expressão da linha, ordenação)
TABLES = [("auth_users", "auth.users x", "to_jsonb(x)", "x.id"),
          ("profiles", "public.profiles x", "to_jsonb(x)", "x.id"),
          ("teams", "public.teams x", "to_jsonb(x)", "x.id"),
          ("profile_modules", "public.profile_modules x", "to_jsonb(x)", "x.id"),
          ("team_members", "public.team_members x", "to_jsonb(x)", "x.id"),
          ("contracts", "public.contracts x", "to_jsonb(x)", "x.id"),
          ("proposals", "public.proposals x", "to_jsonb(x)", "x.id"),
          ("billing_entities", "public.billing_entities x", "to_jsonb(x)", "x.id"),
          ("clients", "public.clients x", "to_jsonb(x)", "x.id"),
          ("projects", "public.projects x", "to_jsonb(x)", "x.id"),
          ("service_types", "public.service_types x", "to_jsonb(x)", "x.id"),
          ("contract_installments", "public.contract_installments x", "to_jsonb(x)", "x.id"),
          ("contract_revenue_splits", "public.contract_revenue_splits x", "to_jsonb(x)", "x.id"),
          ("bank_transactions", "public.bank_transactions x", "to_jsonb(x)", "x.id"),
          ("taxpayer_profiles", "public.taxpayer_profiles x", "to_jsonb(x)", "x.id"),
          ("billing_contacts", "public.billing_contacts x", "to_jsonb(x)", "x.id"),
          ("contract_fiscal_settings", "public.contract_fiscal_settings x", "to_jsonb(x)", "x.id"),
          ("company_tax_regimes", "public.company_tax_regimes x", "to_jsonb(x)", "x.valid_from"),
          ("dre_tax_rates", "public.dre_tax_rates x", "to_jsonb(x)", "x.month"),
          ("reimbursement_reports", "public.reimbursement_reports x", "to_jsonb(x)", "x.id"),
          ("reimbursement_items", "public.reimbursement_items x",
           "(to_jsonb(x) - 'approved_amount' - 'approval_note')", "x.id"),
          ("reimbursement_rate_rules", "public.reimbursement_rate_rules x", "to_jsonb(x)", "x.id"),
          ("expense_categories", "public.expense_categories x", "to_jsonb(x)", "x.id"),
          ("allocation_rules", "public.allocation_rules x", "to_jsonb(x)", "x.id"),
          ("allocation_rule_splits", "public.allocation_rule_splits x", "to_jsonb(x)", "x.id"),
          ("team_cost_allocations", "public.team_cost_allocations x", "to_jsonb(x)", "x.id")]

results = []


def abort(msg):
    print(f"ABORTADO: {msg}")
    sys.exit(2)


def record(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK     ' if ok else 'FALHOU '} {name}{' -- ' + detail if detail and not ok else ''}")


def load_env():
    vals = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    if not vals.get("DATABASE_URL"):
        abort("DATABASE_URL não encontrado em backend/.env")
    return vals


async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


def fmt(fp):
    return f"{fp[0]} (md5 {fp[1][:12]}…)"


async def fingerprints(c):
    out = {}
    for key, source, expr, order in TABLES:
        row = await c.fetchrow(
            f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by {order}), '')) as h "
            f"from {source}")
        out[key] = (row["n"], row["h"])
    out["close_deal"] = await c.fetchval(CLOSE_DEAL_MD5_SQL)
    return out


async def triggers(c):
    return {r["name"]: r["enabled"] for r in await c.fetch(TRIGGERS_SQL)}


async def diego_fp(c, diego):
    return await c.fetchval(
        "select md5(coalesce((select row_to_json(p)::text from public.profiles p where p.id = $1), '') || '|' || "
        "coalesce((select string_agg(module, ',' order by module) from public.profile_modules "
        "where profile_id = $1), ''))", diego)


async def master_ids(c):
    return [r["id"] for r in await c.fetch("select id from public.profiles where system_role = 'master'")]


# ---------- travas + medição + aplicação ----------
async def apply(dsn, sql, master_email):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("prod"))
    try:
        num = int(await c.fetchval("show server_version_num"))
        print(f"server_version_num: {num}")
        if num < 150000:
            abort("Postgres anterior ao 15")
        if not await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                                "and table_name = 'reimbursement_items' and column_name = 'receipt_path') "
                                "and to_regprocedure('public.fn_reimbursement_items_validate_total()') is not null"):
            abort("a 052 não está aplicada (receipt_path ou fn_reimbursement_items_validate_total ausente)")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'reimbursement_items' and column_name = 'approved_amount') "
                            "or to_regprocedure($1::text) is not null "
                            "or exists (select 1 from pg_policies where schemaname = 'public' "
                            "and tablename = 'reimbursement_items' and policyname = $2::text)", GUARD_FN, NEW_POLICY):
            abort("a 053 parece já aplicada (approved_amount, a função de guarda ou a policy nova existe)")

        rows = await c.fetch("select id from auth.users where lower(email) = lower($1::text)", master_email)
        if len(rows) != 1:
            abort(f"esperada 1 conta com o MASTER_EMAIL, achou {len(rows)}")
        diego = rows[0]["id"]
        m = await master_ids(c)
        print(f"masters em profiles: {len(m)}")
        if len(m) != 1:
            abort(f"esperado exatamente 1 master, achou {len(m)}")
        if m[0] != diego:
            abort("o master existente não é a conta do Diego (resolvida pelo MASTER_EMAIL)")
        print("master existente = conta do Diego (resolvida pelo MASTER_EMAIL)")

        before = await fingerprints(c)
        before["diego"] = await diego_fp(c, diego)
        before["triggers"] = await triggers(c)
        before["policies"] = await c.fetchval(POLICIES_SQL, NEW_POLICY)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _, _ in TABLES)
              + f"; close_deal md5 {before['close_deal'][:12]}…; Diego md5 {before['diego'][:12]}…"
              f"; gatilhos: {sorted(before['triggers'])}; policies md5 {before['policies'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n053 aplicada e COMMIT feito.\n")
        return diego, before
    finally:
        await c.close()


# ---------- conferência em conexão nova ----------
async def verify_structure(c, before):
    got = await c.fetchrow(COL_SQL, "approved_amount")
    got = tuple(got) if got else None
    record("V1 reimbursement_items.approved_amount: numeric, aceita nulo, sem padrão",
           got == ("numeric", "YES", None), f"veio {got!r}")
    got = await c.fetchrow(COL_SQL, "approval_note")
    got = tuple(got) if got else None
    record("V2 reimbursement_items.approval_note: text, aceita nulo, sem padrão",
           got == ("text", "YES", None), f"veio {got!r}")
    await check(c, f"V3 check {CHECK_NAME} (approved_amount nulo ou >= 0)",
                "select count(*) from pg_constraint where conrelid = 'public.reimbursement_items'::regclass "
                "and conname = $1::text and contype = 'c' and pg_get_constraintdef(oid) like '%approved_amount >= %'",
                1, CHECK_NAME)
    # tgtype 23 = ROW (1) + BEFORE (2) + INSERT (4) + UPDATE (16); sem UPDATE OF
    await check(c, "V4 trg_reimbursement_items_guard_approved_amount: BEFORE INSERT OR UPDATE (todo UPDATE), ligado",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_items_guard_approved_amount' "
                "and tgrelid = 'public.reimbursement_items'::regclass and tgtype = 23 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text) and pg_get_triggerdef(oid) not like '%UPDATE OF%'",
                1, GUARD_FN)
    await check(c, "V5 função de guarda: security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, GUARD_FN)
    no_public = ("not exists (select 1 from pg_proc p, aclexplode(p.proacl) a where p.oid = to_regprocedure($1::text) "
                 "and a.grantee = 0 and a.privilege_type = 'EXECUTE')")
    await check(c, "V6 função de guarda: sem EXECUTE para anon, PUBLIC e authenticated",
                "select not has_function_privilege('anon'::name, $1::text, 'execute') "
                f"and not has_function_privilege('authenticated'::name, $1::text, 'execute') and {no_public}",
                True, GUARD_FN)
    await check(c, "V7 policy reimbursement_items_approve_amount: UPDATE, master, 'enviado', não o próprio",
                "select cmd = 'UPDATE' and qual like '%is_master()%' and qual like '%enviado%' "
                "and qual like '%profile_id <> auth.uid()%' and with_check like '%is_master()%' "
                "and with_check like '%profile_id <> auth.uid()%' from pg_policies where schemaname = 'public' "
                "and tablename = 'reimbursement_items' and policyname = $1::text", True, NEW_POLICY)
    await check(c, "V8 as demais policies de itens e relatórios iguais às de antes", POLICIES_SQL,
                before["policies"], NEW_POLICY)
    after = await triggers(c)
    kept = all(after.get(n) == "O" for n in before["triggers"])
    extra = sorted(set(after) - set(before["triggers"]))
    record("V9 gatilhos que já existiam continuam ligados, e só o novo foi acrescentado",
           kept and extra == [NEW_TRIGGER], f"antes {sorted(before['triggers'])}, depois {sorted(after)}")
    await check(c, "V10 nenhum item existente com approved_amount ou approval_note preenchido",
                "select count(*) from public.reimbursement_items "
                "where approved_amount is not null or approval_note is not null", 0)


async def verify(dsn, diego, before):
    c = await asyncpg.connect(dsn=dsn, ssl=_lib.ssl_ctx("prod"))
    try:
        async with c.transaction(readonly=True):
            print(f"[conexão nova] transaction_read_only: {await c.fetchval('show transaction_read_only')}")
            await verify_structure(c, before)

            print("\n== dados (comparados com a medição antes do COMMIT) ==")
            after = await fingerprints(c)
            for key, _, _, _ in TABLES:
                record(f"D1 {key}: igual ao começo (contagem + md5)", after[key] == before[key],
                       f"antes {fmt(before[key])}, depois {fmt(after[key])}")
            record("D2 corpo do close_deal igual ao começo (md5)", after["close_deal"] == before["close_deal"])
            record("D3 perfil e módulos do Diego iguais ao começo (md5)", await diego_fp(c, diego) == before["diego"])
            m = await master_ids(c)
            record("D4 masters = 1 e é o Diego", m == [diego], f"{len(m)} master(s)")

            if after["auth_users"] != before["auth_users"]:
                print("\nAVISO: auth.users mudou. Pode ser login real durante a aplicação "
                      "(last_sign_in_at/updated_at), não necessariamente a 053. Para decidir:")
                for key in ("profiles", "teams"):
                    print(f"  {key}: antes {fmt(before[key])}, depois {fmt(after[key])}, "
                          f"igual: {after[key] == before[key]}")
                print(f"  auth_users: antes {fmt(before['auth_users'])}, depois {fmt(after['auth_users'])}, "
                      f"contagem igual: {after['auth_users'][0] == before['auth_users'][0]}")
    finally:
        await c.close()


async def main():
    env = load_env()
    dsn = env["DATABASE_URL"]
    if REQUIRED_HOST not in dsn:
        abort(f"DATABASE_URL não contém {REQUIRED_HOST}: não é produção")
    if PROD_REF not in dsn:
        abort("DATABASE_URL não contém a ref de produção")
    if STAGING_REF in dsn:
        abort("DATABASE_URL contém a ref de STAGING")
    master_email = env.get("MASTER_EMAIL", "")
    if "@" not in master_email:
        abort("MASTER_EMAIL ausente ou inválido em backend/.env")

    sql = MIGRATION.read_text(encoding="utf-8")
    if re.search(r"^\s*(begin|commit|rollback)\s*;", sql, re.I | re.M):
        abort("a migration tem begin/commit/rollback no nível de topo")

    diego, before = await apply(dsn, sql, master_email)
    await verify(dsn, diego, before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
