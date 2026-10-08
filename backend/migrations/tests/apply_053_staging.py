"""Aplica a 053 em STAGING com COMMIT real, depois confere numa conexão nova
(READ ONLY). Não imprime e-mails, DSN nem chaves; dos dados, só contagens e
os 12 primeiros caracteres dos md5.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/apply_053_staging.py

Travas (todas antes de gravar):
  1. DATABASE_URL de backend/.env.staging com us-west-2 e a ref de staging,
     sem a ref de produção (antes de conectar).
  2. A migration não tem begin/commit/rollback no nível de topo (antes de conectar).
  3. server_version_num >= 150000.
  4. A 052 está aplicada (reimbursement_items.receipt_path e
     fn_reimbursement_items_validate_total existem).
  5. A 053 ainda não está aplicada (approved_amount ausente, função de guarda
     e policy reimbursement_items_approve_amount inexistentes).
Antes de gravar mede: contagem + md5 (linha inteira, ordenada por id) de
reimbursement_items (sem approved_amount e approval_note), reimbursement_reports,
reimbursement_rate_rules, expense_categories, allocation_rules e
allocation_rule_splits; as policies de reimbursement_items e
reimbursement_reports (md5); e os gatilhos que já existem nas duas tabelas
(nome e se estão ligados).
Aplicação: o arquivo inteiro numa transação única; o COMMIT acontece só ao
sair do bloco sem erro (não há chamada de commit escrita). Se qualquer parte
falhar, nada fica gravado.
Os testes funcionais (I, K, M, O, S, N, E, T do test_053_staging.py) não se
repetem aqui: já passaram 45/45 dentro de transação desfeita. Aqui só
estrutura e dados; as consultas de estrutura são as mesmas do bloco A do teste.

Verificações esperadas na conexão nova: 16
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
  + D1 tabela igual ao começo (contagem + md5) x 6 tabelas 6
  = 16
"""
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

import _lib

ROOT = Path(r"C:\Users\pmon_admin\Documents\gestao-obras\backend")
ENV = ROOT / ".env.staging"
MIGRATION = ROOT / "migrations" / "053_reimbursement_approved_amount.sql"
REQUIRED_HOST = "us-west-2"
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
# (chave, origem com alias x, expressão da linha)
TABLES = [("reimbursement_items", "public.reimbursement_items x",
           "(to_jsonb(x) - 'approved_amount' - 'approval_note')"),
          ("reimbursement_reports", "public.reimbursement_reports x", "to_jsonb(x)"),
          ("reimbursement_rate_rules", "public.reimbursement_rate_rules x", "to_jsonb(x)"),
          ("expense_categories", "public.expense_categories x", "to_jsonb(x)"),
          ("allocation_rules", "public.allocation_rules x", "to_jsonb(x)"),
          ("allocation_rule_splits", "public.allocation_rule_splits x", "to_jsonb(x)")]

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
                                "and table_name = 'reimbursement_items' and column_name = 'receipt_path') "
                                "and to_regprocedure('public.fn_reimbursement_items_validate_total()') is not null"):
            abort("a 052 não está aplicada (receipt_path ou fn_reimbursement_items_validate_total ausente)")
        if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'reimbursement_items' and column_name = 'approved_amount') "
                            "or to_regprocedure($1::text) is not null "
                            "or exists (select 1 from pg_policies where schemaname = 'public' "
                            "and tablename = 'reimbursement_items' and policyname = $2::text)", GUARD_FN, NEW_POLICY):
            abort("a 053 parece já aplicada (approved_amount, a função de guarda ou a policy nova existe)")

        before = await fingerprints(c)
        before["triggers"] = await triggers(c)
        before["policies"] = await c.fetchval(POLICIES_SQL, NEW_POLICY)
        print("antes: " + ", ".join(f"{k}={fmt(before[k])}" for k, _, _ in TABLES)
              + f"; gatilhos: {sorted(before['triggers'])}; policies md5 {before['policies'][:12]}…")

        async with c.transaction():
            await c.execute(sql)
        print("\n053 aplicada e COMMIT feito.\n")
        return before
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
