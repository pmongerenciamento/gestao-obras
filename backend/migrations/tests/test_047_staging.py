"""Teste da migration 047 no STAGING (que já tem a 045 e a 046 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_047_staging.py

Por que um script só: o staging já tem a 045 e a 046 com COMMIT, e os testes
delas abortam de propósito quando a migration já existe. Aqui a 047 é
aplicada dentro da transação e, sobre ela, rodam: (s) os casos SP1 a SP10 da
045 adaptados a set_contract_splits(contrato, valid_from, itens, retroativo);
a bateria funcional da 046 (a a g, CD, H) com um helper que grava uma versão
de divisão em cada contrato antes de gerar/estender; (w) e (v) os casos
novos da 047.

Regras:
- Só roda com DATABASE_URL de backend/.env.staging com us-west-2 e a ref de
  staging, sem a ref de produção (checado antes de qualquer conexão).
- Aborta se server_version_num < 150000, se a 046 não estiver aplicada ou se
  a 047 já estiver (contract_revenue_splits.valid_from existe).
- Aplica a 047 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint que falha são
  desfeitos junto com ele.
- Usuários fictícios @example.invalid; nada de e-mail, senha, chave ou DSN
  impresso. Nenhum commit.
- O horizonte da extensão é calculado a partir do current_date do banco.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 194 verificações
  CD0 1 (close_deal antes) + M0 1 + H1 1 + CD1 a CD7 7 (close_deal depois)
  + bateria da 046 com o helper de versão: (a) 10 + (b) 32 + (c) 21
    + (d) 16 + (e) 10 + (f) 6
  + (g) 30 [G1 crm e sem módulo x 5 funções = 10; G2 1; G3 1;
            G4/G5/G6 x 5 funções = 15; G7 x 2 papéis = 2; G8 1]
  + (s) SP1 a SP10 com p_valid_from = 14
  + (w) estrutura da 047 = 11 [W1 a W8, W9 x 2 papéis, W10]
  + (v) vigência das versões = 27
  + pós-rollback L1 a L7 = 7
Se a M0 falhar, o script para logo depois: CD0 + M0 + 7 = 9 verificações.
"""
import asyncio
import calendar
import datetime
import itertools
import json
import secrets
import sys
from decimal import Decimal
from pathlib import Path

import asyncpg

import _lib

REPO = Path(r"C:\Users\pmon_admin\Documents\gestao-obras")
ENV_FILE = REPO / "backend" / ".env.staging"
MIGRATION = REPO / "backend" / "migrations" / "047_split_effective_dating.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste047-" + secrets.token_hex(4)
OLD_SPLITS = "public.set_contract_splits(uuid, jsonb)"
NEW_SPLITS = "public.set_contract_splits(uuid, date, jsonb, boolean)"
SUM_TRIGGER_FN = "public.fn_contract_revenue_splits_sum_100()"
GEN_EXT_MD5_SQL = ("select md5(string_agg(pg_get_functiondef(p.oid), '|' order by p.proname)) from pg_proc p "
                   "where p.pronamespace = 'public'::regnamespace "
                   "and p.proname in ('generate_contract_installments', 'extend_recurring_installments')")
PUBLIC_FUNCS = ["public.generate_contract_installments(uuid, text, text)",
                "public.extend_recurring_installments(uuid)",
                "public.apply_readjustment(uuid, numeric, date, text)",
                "public.confirm_installment_receipt_from_bank(uuid, uuid)",
                "public.confirm_installment_receipt_manual(uuid, date, numeric)"]
HELPER_FUNC = "public.fn_contract_is_revision_point(date, integer, date, date)"
FUNC_NAMES = ["generate_contract_installments", "extend_recurring_installments", "apply_readjustment",
              "confirm_installment_receipt_from_bank", "confirm_installment_receipt_manual",
              "fn_contract_is_revision_point"]
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")

results = []


def abort(msg):
    print(f"ABORTADO: {msg}")
    sys.exit(2)


def record(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'OK     ' if ok else 'FALHOU '} {name}{' -- ' + detail if detail and not ok else ''}")


def read_dsn():
    vals = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    dsn = vals.get("DATABASE_URL", "")
    if "us-west-2" not in dsn:
        abort("DATABASE_URL de backend/.env.staging não é us-west-2")
    if STAGING_REF not in dsn:
        abort("DATABASE_URL não contém a ref de staging")
    if PROD_REF in dsn:
        abort("DATABASE_URL contém a ref de PRODUÇÃO")
    return dsn


def add_months(d, n):
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# ---------- papéis (SET LOCAL, dentro da transação) ----------
async def as_user(c, uid):
    await c.execute("set local role authenticated")
    await c.fetchval("select set_config('request.jwt.claim.sub', $1::text, true), "
                     "set_config('request.jwt.claims', $2::text, true)",
                     str(uid), json.dumps({"sub": str(uid), "role": "authenticated"}))


async def as_authenticated_no_sub(c):
    await c.execute("set local role authenticated")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', $1::text, true)", json.dumps({"role": "authenticated"}))


async def as_anon(c):
    await c.execute("set local role anon")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', $1::text, true)", json.dumps({"role": "anon"}))


async def as_owner(c):
    await c.execute("reset role")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', '', true)")


# ---------- helpers de teste ----------
async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


async def check_row(c, name, sql, expected, *args):
    """Compara a linha como tupla: numeric chega como Decimal e é comparado
    como número (Decimal('800.00') == Decimal('800')), não como texto."""
    row = await c.fetchrow(sql, *args)
    got = tuple(row) if row is not None else None
    record(name, got == tuple(expected), f"esperado {tuple(expected)!r}, veio {got!r}")


async def expect_ok(c, name, fn):
    """fn roda num savepoint; se falhar, o savepoint desfaz tudo (inclusive o papel)."""
    try:
        async with c.transaction():
            r = await fn()
        record(name, True)
        return r
    except asyncpg.PostgresError as e:
        record(name, False, f"erro inesperado {e.sqlstate}: {str(e)[:200]}")
    except AssertionError as e:
        record(name, False, str(e)[:200])
    return None


async def expect_fail(c, name, fn, sqlstate, constraint=None):
    try:
        async with c.transaction():
            await fn()
        record(name, False, "não falhou")
    except asyncpg.PostgresError as e:
        got_c = getattr(e, "constraint_name", None)
        ok = e.sqlstate == sqlstate and (constraint is None or got_c == constraint)
        record(name, ok, f"sqlstate {e.sqlstate} constraint {got_c} ({str(e)[:150]}), "
                         f"esperado {sqlstate}{' / ' + constraint if constraint else ''}")


async def make_user(c, label):
    uid = await c.fetchval(
        "insert into auth.users (id, aud, role, email, created_at, updated_at) "
        "values (gen_random_uuid(), 'authenticated', 'authenticated', $1::text, now(), now()) returning id",
        f"{TAG}-{label}@example.invalid")
    if not await c.fetchval("select exists (select 1 from public.profiles where id = $1)", uid):
        await c.execute("insert into public.profiles (id) values ($1)", uid)
    return uid


async def close_deal_flow(c, uid, *, check_first_due=False):
    """Fluxo de ponta a ponta do close_deal (mesmo do test041.py): cliente,
    projeto, proposta e fechamento como authenticated com módulo crm. Tudo
    num savepoint SEMPRE desfeito. Devolve só fatos comparáveis (sem ids)."""
    sp = c.transaction()
    await sp.start()
    try:
        code = None
        while not code or await c.fetchval("select exists (select 1 from public.clients where code = $1::text)", code):
            code = "Q" + secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        client_id = await c.fetchval(
            "insert into public.clients (code, legal_name) values ($1::text, 'TESTE 047 CD') returning id", code)
        project_id = await c.fetchval(
            "insert into public.projects (name, owner_id, client_id) values ($1::text, $2, $3) returning id",
            f"TESTE 047 CD {TAG}", uid, client_id)
        service_type_id = await c.fetchval("select id from public.service_types order by code limit 1")
        await c.execute("insert into public.proposals (project_id, value, payment_type, service_type_id) "
                        "values ($1, 1000, 'parcela_unica', $2)", project_id, service_type_id)
        await as_user(c, uid)
        contract_id = await c.fetchval(
            "select public.close_deal($1, 'TESTE 047 LTDA', $2::text, 'end', 'rep', '000', 'role', "
            "'SPE TESTE 047', $3::text, 'end spe', null)",
            project_id, "".join(secrets.choice("0123456789") for _ in range(14)),
            "".join(secrets.choice("0123456789") for _ in range(14)))
        await as_owner(c)
        res = {
            "contrato_criado": await c.fetchval("select exists (select 1 from public.contracts where id = $1)",
                                                contract_id),
            "proposta_status": await c.fetchval("select status from public.proposals where project_id = $1",
                                                project_id),
            "projeto_estagio": await c.fetchval("select pipeline_stage from public.projects where id = $1",
                                                project_id),
            "spe_criada": await c.fetchval("select exists (select 1 from public.billing_entities "
                                           "where project_id = $1)", project_id),
            "historico_final": await c.fetchval("select count(*) from public.project_stage_history "
                                                "where project_id = $1", project_id),
            "historico_aberto": await c.fetchval("select stage from public.project_stage_history "
                                                 "where project_id = $1 and exited_at is null", project_id),
        }
        if check_first_due:
            res["first_due_date_nulo"] = await c.fetchval(
                "select first_due_date is null from public.contracts where id = $1", contract_id)
    except asyncpg.PostgresError as e:
        res = {"FALHOU": f"{e.sqlstate}: {str(e)[:200]}"}
    await sp.rollback()
    await as_owner(c)
    return res


# ---------- pré-condições (fora da transação, só leitura) ----------
async def preconditions(c):
    num = int(await c.fetchval("show server_version_num"))
    print(f"server_version_num: {num}")
    if num < 150000:
        abort("Postgres anterior ao 15")
    if not await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                            "and table_name = 'contracts' and column_name = 'first_due_date') "
                            "and to_regprocedure('public.generate_contract_installments(uuid, text, text)') is not null"):
        abort("a 046 não está aplicada")
    if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contract_revenue_splits' and column_name = 'valid_from')"):
        abort("a 047 parece já aplicada (contract_revenue_splits.valid_from existe)")
    if not await c.fetchval("select to_regprocedure($1::text) is not null", OLD_SPLITS):
        abort("set_contract_splits(uuid, jsonb) da 045 não existe")
    print(f"contract_revenue_splits antes da 047: "
          f"{await c.fetchval('select count(*) from public.contract_revenue_splits')} linha(s)")
    return await c.fetchval(CLOSE_DEAL_MD5_SQL), await c.fetchval(GEN_EXT_MD5_SQL)


async def run_tests(c, sql, close_deal_before):
    # close_deal de ponta a ponta ANTES da 047 (usuário fictício com crm)
    cd_user = await make_user(c, "cd")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'crm')", cd_user)
    cd_before = await close_deal_flow(c, cd_user)
    record("CD0 close_deal antes da 047 executa sem erro", "FALHOU" not in cd_before, str(cd_before))

    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 047 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 047 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # (h) close_deal intacto
    await check(c, "H1 close_deal com o mesmo md5 do corpo antes e depois da 047", CLOSE_DEAL_MD5_SQL,
                close_deal_before)

    # close_deal de ponta a ponta DEPOIS da 047
    cd_after = await close_deal_flow(c, cd_user, check_first_due=True)
    record("CD1 close_deal depois da 047 executa sem erro", "FALHOU" not in cd_after, str(cd_after))
    record("CD2 depois: contrato criado", cd_after.get("contrato_criado") is True, str(cd_after))
    record("CD3 depois: proposta aceita", cd_after.get("proposta_status") == "aceita", str(cd_after))
    record("CD4 depois: projeto fechado_ganho", cd_after.get("projeto_estagio") == "fechado_ganho", str(cd_after))
    record("CD5 depois: SPE criada", cd_after.get("spe_criada") is True, str(cd_after))
    after_cmp = {k: v for k, v in cd_after.items() if k != "first_due_date_nulo"}
    record("CD6 resultado do fechamento igual antes e depois da 047", after_cmp == cd_before,
           f"antes {cd_before}, depois {after_cmp}")
    record("CD7 contracts.first_due_date fica nulo no contrato criado pelo close_deal",
           cd_after.get("first_due_date_nulo") is True, str(cd_after))

    today = await c.fetchval("select current_date")
    horizon = add_months(datetime.date(today.year, today.month, 1), 13) - datetime.timedelta(days=1)

    # ---------- dados de apoio (dono da migration) ----------
    fin = await make_user(c, "fin")
    crm = await make_user(c, "crm")
    none_ = await make_user(c, "sem")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro'), ($2, 'crm')",
                    fin, crm)
    project = await c.fetchval("insert into public.projects (name, owner_id) values ($1::text, $2) returning id",
                               f"TESTE 047 {TAG}", fin)
    codes = itertools.count(1)
    st = {r["code"]: r["id"] for r in await c.fetch("select id, code from public.service_types")}
    team_a = await c.fetchval("insert into public.teams (name) values ($1::text) returning id", f"TESTE 047 A {TAG}")
    team_b = await c.fetchval("insert into public.teams (name) values ($1::text) returning id", f"TESTE 047 B {TAG}")

    async def run_as(uid, q, *args):
        await as_user(c, uid)
        v = await c.fetchval(q, *args)
        await as_owner(c)
        return v

    SPLITS = "select public.set_contract_splits($1::uuid, ($2::text)::date, $3::jsonb, coalesce($4::boolean, false))"

    def splits(*items):
        return json.dumps([{"share_kind": k, "team_id": str(t) if t else None, "scope": s, "percentage": p}
                           for k, t, s, p in items])

    def set_split(uid, cid, valid_from, payload, allow=None):
        return run_as(uid, SPLITS, cid, valid_from, payload, allow)

    async def contract(payment_type, fee, start, first_due, *, end=None, index="INCC", cycle=12,
                       status="ativo", svc="SVC-002", split="2025-01-01"):
        cid = await c.fetchval(
            """insert into public.contracts (project_id, contract_code, contract_label, service_type_id,
                 payment_type, fee_value, readjustment_index, readjustment_cycle_months, start_date,
                 first_due_date, end_date, status)
               values ($1, $2::text, 'TESTE 047', $3, $4::text, $5::numeric, $6::text, $7::int,
                       ($8::text)::date, ($9::text)::date, ($10::text)::date, $11::text)
               returning id""",
            project, f"{next(codes):02d}", st[svc], payment_type, str(fee), index, cycle,
            start, first_due, end, status)
        # helper da 047: uma versão de divisão (dono 100%) antes de gerar/estender;
        # split=None deixa o contrato sem regra (casos de recusa)
        if split is not None:
            await set_split(fin, cid, split, splits(("dono", team_a, "gerenciamento", 100)))
        return cid

    GEN = "select public.generate_contract_installments($1::uuid, $2::text, coalesce($3::text, 'inter_pj'))"
    EXT = "select public.extend_recurring_installments($1::uuid)"
    APPLY = "select public.apply_readjustment($1::uuid, $2::numeric, ($3::text)::date, 'INCC')"
    BANK = "select public.confirm_installment_receipt_from_bank($1::uuid, $2::uuid)"
    MANUAL = "select public.confirm_installment_receipt_manual($1::uuid, ($2::text)::date, $3::numeric)"

    def gen(cid, rtype=None, acct=None):
        return run_as(fin, GEN, cid, rtype, acct)

    async def dues(cid, where="true"):
        return await c.fetchval(f"select string_agg(due_date::text, ',' order by due_date) "
                                f"from public.contract_installments where contract_id = $1 and {where}", cid)

    async def inst_at(cid, due):
        return await c.fetchval("select id from public.contract_installments where contract_id = $1 "
                                "and due_date = ($2::text)::date and origin = 'projetada'", cid, due)

    async def avulsa(cid, number, due, *, rtype="reembolso", factor="1", status="projetada"):
        return await c.fetchval(
            """insert into public.contract_installments (contract_id, installment_number, revenue_type, origin,
                 due_date, base_amount, readjustment_factor, expected_amount, status, created_by)
               values ($1, $2, $3::text, 'avulsa', ($4::text)::date, 100, $5::numeric, 100, $6::text, $7)
               returning id""", cid, number, rtype, due, factor, status, fin)

    async def bank_tx(kind, value, tdate, *, status="pendente", expense=None, inst=None):
        return await c.fetchval(
            """insert into public.bank_transactions (external_id, transaction_date, value, type,
                 reconciliation_status, matched_expense_id, matched_contract_installment_id)
               values ($1::text, ($2::text)::date, $3::numeric, $4::text, $5::text, $6, $7) returning id""",
            f"{TAG}-{secrets.token_hex(4)}", tdate, str(value), kind, status, expense, inst)

    # ---------- (a) first_due_date e bank_transactions ----------
    await check_row(c, "A1 contracts.first_due_date existe, nula e sem padrão",
                    "select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'contracts' and column_name = 'first_due_date'",
                    ("date", "YES", None))
    await check(c, "A2 FK de matched_contract_installment_id sem on delete",
                "select confdeltype::text from pg_constraint "
                "where conname = 'bank_transactions_matched_contract_installment_id_fkey'", "a")
    await check(c, "A3 índice único parcial em matched_contract_installment_id",
                "select indisunique and indpred is not null from pg_index "
                "where indexrelid = to_regclass('public.uq_bank_transactions_matched_installment')", True)

    a_ctr = await contract("parcela_unica", 500, "2026-01-01", "2026-08-01")
    a_inst = await expect_ok(c, "A4 setup: gera parcela para os testes de bank_transactions",
                             lambda: gen(a_ctr))
    a_inst = await inst_at(a_ctr, "2026-08-01")
    cat = await c.fetchval("select id from public.expense_categories order by name limit 1")
    expense = await c.fetchval(
        "insert into public.expenses (category_id, vendor_name, competencia_month, value, created_by) "
        "values ($1, $2::text, '2026-08-01', 10, $3) returning id", cat, f"TESTE 047 {TAG}", fin)

    await expect_fail(c, "A5 exclusividade: despesa e parcela juntas",
                      lambda: bank_tx("credito", 10, "2026-08-01", expense=expense, inst=a_inst), "23514")
    await expect_fail(c, "A6 direção: despesa em crédito",
                      lambda: bank_tx("credito", 10, "2026-08-01", expense=expense), "23514",
                      "bank_transactions_match_direction_check")
    await expect_fail(c, "A7 direção: parcela em débito",
                      lambda: bank_tx("debito", 10, "2026-08-01", inst=a_inst), "23514",
                      "bank_transactions_match_direction_check")
    await expect_ok(c, "A8 parcela em crédito é aceita",
                    lambda: bank_tx("credito", 10, "2026-08-01", inst=a_inst))

    async def two_on_same():
        await bank_tx("credito", 10, "2026-08-01", inst=a_inst)
        await bank_tx("credito", 10, "2026-08-02", inst=a_inst)
    await expect_fail(c, "A9 unicidade: duas transações na mesma parcela", two_on_same, "23505",
                      "uq_bank_transactions_matched_installment")
    await expect_ok(c, "A10 despesa em débito é aceita",
                    lambda: bank_tx("debito", 10, "2026-08-01", expense=expense))

    # ---------- (b) geração ----------
    pu = await contract("parcela_unica", 1500, "2026-01-01", "2026-08-15")
    n = await expect_ok(c, "B1 parcela única: gera", lambda: gen(pu))
    record("B1b parcela única: devolve 1", n == 1, f"veio {n!r}")
    await check_row(c, "B1c parcela única: vencimento, valores, status, origem, tipo, conta e autor",
                    "select due_date::text, base_amount, readjustment_factor, expected_amount, status, origin, "
                    "revenue_type, destination_account, created_by = $2 "
                    "from public.contract_installments where contract_id = $1",
                    ("2026-08-15", Decimal("1500"), Decimal("1"), Decimal("1500"), "projetada", "projetada",
                     "gerenciamento", "inter_pj", True), pu, fin)

    m12 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-02-10")
    n = await expect_ok(c, "B2 mensal: gera", lambda: gen(m12))
    record("B2b mensal: devolve 12", n == 12, f"veio {n!r}")
    await check_row(c, "B2c mensal: 12 parcelas de 2026-02-10 a 2027-01-10, numeradas 1 a 12",
                    "select count(*), min(due_date)::text, max(due_date)::text, "
                    "min(installment_number), max(installment_number) "
                    "from public.contract_installments where contract_id = $1",
                    (12, "2026-02-10", "2027-01-10", 1, 12), m12)

    d31 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-31")
    await expect_ok(c, "B3 dia 31: gera", lambda: gen(d31))
    v = await dues(d31, "due_date <= '2026-05-31'")
    record("B3b dia 31 (2026): 31/01, 28/02, 31/03, 30/04, 31/05", v ==
           "2026-01-31,2026-02-28,2026-03-31,2026-04-30,2026-05-31", f"veio {v!r}")
    leap = await contract("mensal_recorrente", 1000, "2028-01-01", "2028-01-31")
    await expect_ok(c, "B4 ano bissexto: gera", lambda: gen(leap))
    v = await dues(leap, "due_date <= '2028-03-31'")
    record("B4b bissexto (2028): 31/01, 29/02, 31/03", v == "2028-01-31,2028-02-29,2028-03-31", f"veio {v!r}")

    endc = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-03-05", end="2026-07-20")
    n = await expect_ok(c, "B5 end_date antes dos 12 meses: gera", lambda: gen(endc))
    record("B5b end_date: 5 parcelas (mar a jul)", n == 5, f"veio {n!r}")

    rv = await contract("mensal_recorrente", 1000, "2025-06-10", "2026-01-05")
    await expect_ok(c, "B6 revisão: gera", lambda: gen(rv))
    v = await dues(rv, "is_revision_point")
    record("B6b revisão no 1º vencimento depois do aniversário (10/06/2026 -> 05/07/2026)",
           v == "2026-07-05", f"veio {v!r}")
    rv1 = await contract("mensal_recorrente", 1000, "2025-01-10", "2026-03-01")
    await expect_ok(c, "B6c revisão com 1º vencimento já depois do aniversário: gera", lambda: gen(rv1))
    v = await dues(rv1, "is_revision_point")
    record("B6d revisão na 1ª parcela e no aniversário seguinte (01/03/2026 e 01/02/2027)",
           v == "2026-03-01,2027-02-01", f"veio {v!r}")
    noidx = await contract("mensal_recorrente", 1000, "2025-06-10", "2026-01-05", index=None)
    await expect_ok(c, "B7 sem índice: gera", lambda: gen(noidx))
    await check(c, "B7b sem índice: nenhum ponto de revisão",
                "select count(*) from public.contract_installments where contract_id = $1 and is_revision_point",
                0, noidx)
    cyc0 = await contract("mensal_recorrente", 1000, "2025-06-10", "2026-01-05", cycle=0)
    await expect_ok(c, "B8 ciclo 0: gera sem divisão por zero", lambda: gen(cyc0))
    await check(c, "B8b ciclo 0: nenhum ponto de revisão",
                "select count(*) from public.contract_installments where contract_id = $1 and is_revision_point",
                0, cyc0)

    parc = await contract("parcelado", 6000, "2026-01-01", "2026-02-01")
    await expect_fail(c, "B9 parcelado recusado", lambda: gen(parc), "0A000")
    nofd = await contract("mensal_recorrente", 1000, "2026-01-01", None)
    await expect_fail(c, "B10 sem first_due_date recusado", lambda: gen(nofd), "55000")
    await expect_fail(c, "B11 já gerado recusado", lambda: gen(m12), "55000")
    outros = await contract("parcela_unica", 300, "2026-01-01", "2026-09-01", svc="SVC-005")
    await expect_fail(c, "B12 sem tipo de receita (Outros, sem p_revenue_type) recusado", lambda: gen(outros), "22023")
    await expect_ok(c, "B12b com p_revenue_type informado gera", lambda: gen(outros, "auditoria"))
    await check(c, "B12c tipo informado gravado",
                "select revenue_type from public.contract_installments where contract_id = $1", "auditoria", outros)
    enc = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-02-01", status="encerrado")
    await expect_fail(c, "B13 contrato encerrado recusado", lambda: gen(enc), "55000")
    sus = await contract("parcela_unica", 1000, "2026-01-01", "2026-02-01", status="suspenso")
    await expect_ok(c, "B13b contrato suspenso gera", lambda: gen(sus))
    av = await contract("parcela_unica", 1000, "2026-01-01", "2026-05-01")
    await avulsa(av, 1, "2026-04-01")
    await expect_ok(c, "B14 avulsa existente não bloqueia a geração", lambda: gen(av))
    await check(c, "B14b numeração continua depois da avulsa",
                "select installment_number from public.contract_installments where contract_id = $1 "
                "and origin = 'projetada'", 2, av)
    r3 = await contract("parcela_unica", "1000.555", "2026-01-01", "2026-06-01")
    await expect_ok(c, "B15 fee_value com 3 casas: gera", lambda: gen(r3))
    await check(c, "B15b fee_value arredondado para 2 casas",
                "select base_amount from public.contract_installments where contract_id = $1", Decimal("1000.56"), r3)

    # ---------- (c) extensão ----------
    ext = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_ok(c, "C1 setup: gera 12 para a extensão", lambda: gen(ext))
    first = datetime.date(2026, 1, 10)
    expected_new = 0
    while add_months(first, 12 + expected_new) <= horizon:
        expected_new += 1
    n = await expect_ok(c, f"C2 extensão completa até o horizonte ({horizon})", lambda: run_as(fin, EXT, ext))
    record(f"C2b extensão criou {expected_new} parcela(s)", n == expected_new, f"veio {n!r}")
    await check(c, "C2c última parcela é a última dentro do horizonte",
                "select max(due_date)::text from public.contract_installments where contract_id = $1",
                add_months(first, 11 + expected_new).isoformat(), ext)
    n = await expect_ok(c, "C3 segunda chamada seguida", lambda: run_as(fin, EXT, ext))
    record("C3b idempotente: segunda chamada cria 0", n == 0, f"veio {n!r}")
    ann = await dues(ext, "is_revision_point")
    record("C4 extensão marca o ponto de revisão novo (aniversário 01/01/2027 -> 10/01/2027)",
           ann == "2027-01-10", f"veio {ann!r}")
    await c.execute("delete from public.contract_installments where contract_id = $1 "
                    "and due_date = '2026-06-10'", ext)
    n = await expect_ok(c, "C5 extensão depois de apagar uma projetada", lambda: run_as(fin, EXT, ext))
    record("C5b não duplica: cria 0 e nenhum vencimento repetido",
           n == 0 and await c.fetchval("select count(*) = count(distinct due_date) from public.contract_installments "
                                       "where contract_id = $1", ext), f"criou {n!r}")

    ext2 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", index=None)
    await expect_ok(c, "C6 setup: gera 12 para herança de fator", lambda: gen(ext2))
    await c.execute("update public.contract_installments set readjustment_factor = 1.05, expected_amount = 1050 "
                    "where contract_id = $1 and due_date = '2026-12-10'", ext2)
    await expect_ok(c, "C6b extensão do contrato com fator 1,05", lambda: run_as(fin, EXT, ext2))
    await check(c, "C6c novas herdam fator 1,05 e expected = round(base x fator, 2)",
                "select bool_and(readjustment_factor = 1.05 and expected_amount = round(base_amount * 1.05, 2)) "
                "and count(*) > 0 from public.contract_installments where contract_id = $1 and due_date > '2026-12-10'",
                True, ext2)

    ext3 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", index=None)
    await expect_ok(c, "C7 setup: gera 12 para o caso da avulsa", lambda: gen(ext3))
    await avulsa(ext3, 99, "2027-12-20", factor="2")
    await expect_ok(c, "C7b extensão com avulsa de fator 2 mais à frente", lambda: run_as(fin, EXT, ext3))
    await check(c, "C7c não herda da avulsa: novas com fator 1 e tipo gerenciamento",
                "select bool_and(readjustment_factor = 1 and revenue_type = 'gerenciamento') and count(*) > 0 "
                "from public.contract_installments where contract_id = $1 and origin = 'projetada' "
                "and due_date > '2026-12-10'", True, ext3)

    await expect_fail(c, "C8 extensão recusa parcela única", lambda: run_as(fin, EXT, pu), "55000")
    encx = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_ok(c, "C9 setup: gera para o caso encerrado", lambda: gen(encx))
    await c.execute("update public.contracts set status = 'encerrado' where id = $1", encx)
    await expect_fail(c, "C9b extensão recusa contrato encerrado", lambda: run_as(fin, EXT, encx), "55000")
    past = await contract("mensal_recorrente", 1000, "2025-01-01", "2025-01-10", end="2025-12-31")
    await expect_ok(c, "C10 setup: gera para o caso end_date passado", lambda: gen(past))
    await expect_fail(c, "C10b extensão recusa end_date já passado", lambda: run_as(fin, EXT, past), "55000")
    noproj = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_fail(c, "C11 extensão recusa contrato sem projetadas", lambda: run_as(fin, EXT, noproj), "55000")

    # ---------- (d) reajuste ----------
    rj = await contract("mensal_recorrente", 1000, "2025-06-10", "2026-01-05")
    await expect_ok(c, "D1 setup: gera 12 com revisão em 05/07/2026", lambda: gen(rj))
    await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                    "where contract_id = $1 and due_date in ('2026-03-05', '2026-09-05')", rj)
    await avulsa(rj, 50, "2026-11-20")
    rev = await inst_at(rj, "2026-07-05")
    n = await expect_ok(c, "D2 aplica 4,53% na revisão", lambda: run_as(fin, APPLY, rev, "4.53", "2026-06-01"))
    record("D2b recalculou 5 projetadas (jul, ago, out, nov, dez)", n == 5, f"veio {n!r}")
    await check(c, "D3 projetadas a partir da revisão com fator 1,0453 e expected recalculado",
                "select string_agg(due_date::text, ',' order by due_date) from public.contract_installments "
                "where contract_id = $1 and readjustment_factor = 1.0453 "
                "and expected_amount = round(base_amount * 1.0453, 2)",
                "2026-07-05,2026-08-05,2026-10-05,2026-11-05,2026-12-05", rj)
    await check(c, "D4 anteriores, emitidas e avulsa ficaram com fator 1",
                "select count(*) from public.contract_installments where contract_id = $1 "
                "and readjustment_factor = 1", 8, rj)
    await check_row(c, "D5 linha em contract_readjustments (antes 1, depois 1,0453, 4,53, autor)",
                    "select factor_before, factor_after, percentage, applied_by = $2, reference_month::text "
                    "from public.contract_readjustments where revision_installment_id = $1",
                    (Decimal("1"), Decimal("1.0453"), Decimal("4.53"), True, "2026-06-01"), rev, fin)
    await expect_fail(c, "D6 reajuste duplicado recusado",
                      lambda: run_as(fin, APPLY, rev, "1", "2026-06-01"), "23505")
    await expect_fail(c, "D10 apagar parcela de revisão com reajuste aplicado é recusado",
                      lambda: c.execute("delete from public.contract_installments where id = $1", rev), "23503",
                      "contract_readjustments_installment_same_contract")
    # com a 047 o contrato também tem versão de divisão (FK sem cascade): qualquer
    # uma das duas FKs pode disparar primeiro, então confere só o 23503
    await expect_fail(c, "D11 apagar contrato com parcelas e divisão é recusado (FK sem cascade)",
                      lambda: c.execute("delete from public.contracts where id = $1", m12), "23503")

    rj2 = await contract("mensal_recorrente", 1000, "2025-01-10", "2026-03-01")
    await expect_ok(c, "D7 setup: gera com revisões em 01/03/2026 e 01/02/2027", lambda: gen(rj2))
    late = await inst_at(rj2, "2027-02-01")
    early = await inst_at(rj2, "2026-03-01")
    await expect_ok(c, "D7b aplica primeiro a revisão posterior",
                    lambda: run_as(fin, APPLY, late, "3", "2027-01-01"))
    await expect_fail(c, "D7c revisão anterior depois da posterior recusada (ordem cronológica)",
                      lambda: run_as(fin, APPLY, early, "3", "2026-02-01"), "55000")
    not_rev = await inst_at(rj, "2026-08-05")
    await expect_fail(c, "D8 parcela que não é revisão recusada",
                      lambda: run_as(fin, APPLY, not_rev, "1", "2026-06-01"), "55000")
    rj3 = await contract("mensal_recorrente", 1000, "2025-06-10", "2026-01-05")
    await expect_ok(c, "D9 setup: gera para percentual e mês inválidos", lambda: gen(rj3))
    rev3 = await inst_at(rj3, "2026-07-05")
    await expect_fail(c, "D9b percentual com 5 casas recusado",
                      lambda: run_as(fin, APPLY, rev3, "4.12345", "2026-06-01"), "22023")
    await expect_fail(c, "D9c mês de referência fora do dia 1 recusado",
                      lambda: run_as(fin, APPLY, rev3, "4.5", "2026-06-15"), "22023")

    # ---------- (e) confirmação pelo banco ----------
    bk = await contract("parcela_unica", "1234.50", "2026-01-01", "2026-08-20")
    await expect_ok(c, "E1 setup: parcela em inter_pj", lambda: gen(bk))
    bk_inst = await inst_at(bk, "2026-08-20")
    bkpf = await contract("parcela_unica", "800", "2026-01-01", "2026-08-25")
    await expect_ok(c, "E2 setup: parcela em pf_diego", lambda: gen(bkpf, None, "pf_diego"))
    pf_inst = await inst_at(bkpf, "2026-08-25")
    tx_deb = await bank_tx("debito", "1234.50", "2026-08-20")
    tx_done = await bank_tx("credito", "1234.50", "2026-08-20", status="conciliado")
    tx_ok = await bank_tx("credito", "1234.50", "2026-08-21")
    tx_ok2 = await bank_tx("credito", "1234.50", "2026-08-22")
    await expect_fail(c, "E3 recusa débito", lambda: run_as(fin, BANK, tx_deb, bk_inst), "22023")
    await expect_fail(c, "E4 recusa transação já conciliada", lambda: run_as(fin, BANK, tx_done, bk_inst), "55000")
    await expect_fail(c, "E5 recusa parcela em conta PF", lambda: run_as(fin, BANK, tx_ok, pf_inst), "55000")
    await expect_ok(c, "E6 confirma crédito com parcela do Inter", lambda: run_as(fin, BANK, tx_ok, bk_inst))
    await check_row(c, "E6b parcela recebida com data e valor da transação",
                    "select status, received_date::text, received_amount from public.contract_installments "
                    "where id = $1", ("recebida", "2026-08-21", Decimal("1234.50")), bk_inst)
    await check_row(c, "E6c transação conciliada com parcela, autor e data",
                    "select reconciliation_status, matched_contract_installment_id = $2, "
                    "reconciled_by = $3, reconciled_at is not null from public.bank_transactions where id = $1",
                    ("conciliado", True, True, True), tx_ok, bk_inst, fin)
    await expect_fail(c, "E7 recusa parcela já recebida", lambda: run_as(fin, BANK, tx_ok2, bk_inst), "55000")
    await expect_fail(c, "E8 índice único: segunda transação na mesma parcela",
                      lambda: c.execute("update public.bank_transactions set matched_contract_installment_id = $1 "
                                        "where id = $2", bk_inst, tx_ok2), "23505",
                      "uq_bank_transactions_matched_installment")

    # ---------- (f) confirmação manual ----------
    mi = await contract("parcela_unica", "700", "2026-01-01", "2026-09-10")
    await expect_ok(c, "F1 setup: parcela em inter_pj para o manual", lambda: gen(mi))
    mi_inst = await inst_at(mi, "2026-09-10")
    await expect_fail(c, "F2 manual recusa conta do Inter",
                      lambda: run_as(fin, MANUAL, mi_inst, "2026-09-10", "700"), "55000")
    await expect_fail(c, "F3 manual recusa valor zero",
                      lambda: run_as(fin, MANUAL, pf_inst, "2026-08-25", "0"), "22023")
    await expect_ok(c, "F4 manual confirma parcela PF", lambda: run_as(fin, MANUAL, pf_inst, "2026-08-26", "800"))
    await check_row(c, "F4b parcela PF recebida com data e valor informados",
                    "select status, received_date::text, received_amount from public.contract_installments "
                    "where id = $1", ("recebida", "2026-08-26", Decimal("800")), pf_inst)
    await expect_fail(c, "F5 manual recusa parcela já recebida",
                      lambda: run_as(fin, MANUAL, pf_inst, "2026-08-27", "800"), "55000")

    # ---------- (g) permissões ----------
    calls = [("generate", GEN, (noproj, None, None)),
             ("extend", EXT, (ext,)),
             ("apply_readjustment", APPLY, (rev3, "1", "2026-06-01")),
             ("confirm_from_bank", BANK, (tx_ok2, mi_inst)),
             ("confirm_manual", MANUAL, (mi_inst, "2026-09-10", "700"))]
    for who, uid in (("crm", crm), ("sem módulo", none_)):
        for fname, q, args in calls:
            await expect_fail(c, f"G1 {who} recusado em {fname}", lambda q=q, args=args, uid=uid: run_as(uid, q, *args),
                              "42501")

    async def gen_without_sub():
        await as_authenticated_no_sub(c)
        await c.fetchval(GEN, noproj, None, None)
    await expect_fail(c, "G2 authenticated sem auth.uid() recusado", gen_without_sub, "42501")

    async def gen_as_anon():
        await as_anon(c)
        await c.fetchval(GEN, noproj, None, None)
    await expect_fail(c, "G3 anon não executa generate", gen_as_anon, "42501")

    for f in PUBLIC_FUNCS:
        short = f.split(".")[1].split("(")[0]
        await check(c, f"G4 anon sem EXECUTE em {short}",
                    "select has_function_privilege('anon'::name, $1::text, 'execute')", False, f)
        await check(c, f"G5 authenticated com EXECUTE em {short}",
                    "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, f)
        await check(c, f"G6 PUBLIC sem EXECUTE em {short}",
                    "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                    "where p.oid = ($1::text)::regprocedure and a.grantee = 0", 0, f)
    for role in ("anon", "authenticated"):
        await check(c, f"G7 {role} sem EXECUTE na auxiliar fn_contract_is_revision_point",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, HELPER_FUNC)
    await check(c, "G8 auxiliar é immutable",
                "select provolatile::text from pg_proc where oid = ($1::text)::regprocedure", "i", HELPER_FUNC)

    # ---------- (s) SP1 a SP10 da 045, com p_valid_from ----------
    async def set_split_imm(uid, cid, vf, payload, allow=None):
        """grava a versão e força o trigger adiado de soma 100 a conferir já"""
        await as_user(c, uid)
        n = await c.fetchval(SPLITS, cid, vf, payload, allow)
        await c.execute("set constraints all immediate")
        await c.execute("set constraints all deferred")
        await as_owner(c)
        return n

    VF = "2026-01-01"
    sp_ctr = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", split=None)
    sp_ctr2 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", split=None)
    p_8020 = splits(("dono", team_a, "gerenciamento", 80), ("a_parte", None, "planejamento", 20))
    n = await expect_ok(c, "SP1 80/20 válido numa chamada só (financeiro)", lambda: set_split_imm(fin, sp_ctr, VF, p_8020))
    record("SP1b devolveu 2 linhas", n == 2, f"veio {n!r}")
    await expect_fail(c, "SP2 soma 90 é recusada",
                      lambda: set_split_imm(fin, sp_ctr, VF, splits(("dono", team_a, "g", 70), ("a_parte", None, "p", 20))),
                      "23514")
    await check_row(c, "SP2b versão do SP1 continua intacta (2 linhas, soma 100)",
                    "select count(*), sum(percentage) from public.contract_revenue_splits "
                    "where contract_id = $1 and valid_from = ($2::text)::date", (2, Decimal("100")), sp_ctr, VF)
    await expect_ok(c, "SP3 lista vazia remove a versão (contrato sem parcelas)",
                    lambda: set_split_imm(fin, sp_ctr, VF, "[]"))
    await check(c, "SP3b contrato ficou sem linhas",
                "select count(*) from public.contract_revenue_splits where contract_id = $1", 0, sp_ctr)

    async def direct_split_insert_as_fin():
        await as_user(c, fin)
        await c.execute("insert into public.contract_revenue_splits (contract_id, valid_from, share_kind, team_id, "
                        "scope, percentage) values ($1, '2026-01-01', 'dono', $2, 'g', 100)", sp_ctr, team_a)
    await expect_fail(c, "SP4 insert direto em contract_revenue_splits pelo financeiro", direct_split_insert_as_fin,
                      "42501")
    await expect_ok(c, "SP5 a_parte com team_id é aceita",
                    lambda: set_split_imm(fin, sp_ctr, VF, splits(("dono", team_a, "gerenciamento", 80),
                                                                  ("a_parte", team_b, "planejamento", 20))))
    await check(c, "SP5b team_id da a_parte gravado",
                "select team_id from public.contract_revenue_splits where contract_id = $1 and share_kind = 'a_parte'",
                team_b, sp_ctr)
    await expect_fail(c, "SP6 crm não pode chamar set_contract_splits",
                      lambda: set_split_imm(crm, sp_ctr, VF, splits(("dono", team_a, "g", 100))), "42501")
    await expect_fail(c, "SP7 dono sem team_id",
                      lambda: set_split_imm(fin, sp_ctr, VF, splits(("dono", None, "g", 100))), "22023")
    await expect_fail(c, "SP8 percentual com 3 casas",
                      lambda: set_split_imm(fin, sp_ctr, VF, splits(("dono", team_a, "g", 33.333),
                                                                    ("a_parte", None, "p", 66.667))), "22023")
    await expect_fail(c, "SP9 contrato inexistente",
                      lambda: set_split_imm(fin, team_a, VF, splits(("dono", team_a, "g", 100))), "P0002")
    await expect_fail(c, "SP10 duas a_parte iguais na mesma versão pela função",
                      lambda: set_split_imm(fin, sp_ctr2, VF, splits(("a_parte", None, "x", 50), ("a_parte", None, "x", 50))),
                      "23505")

    # ---------- (w) estrutura da 047 ----------
    await check_row(c, "W1 contract_revenue_splits.valid_from: date e not null",
                    "select data_type::text, is_nullable::text from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'contract_revenue_splits' "
                    "and column_name = 'valid_from'", ("date", "NO"))
    await check(c, "W2 check de dia 1 em valid_from existe",
                "select count(*) from pg_constraint where conname = 'contract_revenue_splits_valid_from_day1' "
                "and contype = 'c'", 1)
    await check(c, "W3 unicidade inclui valid_from (nulls not distinct)",
                "select pg_get_constraintdef(oid) like '%NULLS NOT DISTINCT%valid_from%' from pg_constraint "
                "where conname = 'contract_revenue_splits_unique'", True)
    await check(c, "W4 assinatura antiga set_contract_splits(uuid, jsonb) não existe",
                "select to_regprocedure($1::text) is null", True, OLD_SPLITS)
    await check(c, "W5 assinatura nova existe", "select to_regprocedure($1::text) is not null", True, NEW_SPLITS)
    await check(c, "W6 anon sem EXECUTE na nova set_contract_splits",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, NEW_SPLITS)
    await check(c, "W7 PUBLIC sem EXECUTE na nova set_contract_splits",
                "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                "where p.oid = ($1::text)::regprocedure and a.grantee = 0", 0, NEW_SPLITS)
    await check(c, "W8 authenticated com EXECUTE na nova set_contract_splits",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, NEW_SPLITS)
    for role in ("anon", "authenticated"):
        await check(c, f"W9 {role} continua sem EXECUTE na função de soma 100",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, SUM_TRIGGER_FN)
    await check(c, "W10 trigger de soma 100 continua deferrable initially deferred",
                "select tgdeferrable and tginitdeferred from pg_trigger "
                "where tgname = 'trg_contract_revenue_splits_sum_100'", True)

    # ---------- (v) vigência das versões ----------
    v1 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", split=None)

    async def two_versions():
        await set_split_imm(fin, v1, "2026-01-01", p_8020)
        await set_split_imm(fin, v1, "2026-07-01", splits(("dono", team_a, "gerenciamento", 100)))
    await expect_ok(c, "V1 duas versões em meses diferentes do mesmo contrato", two_versions)
    await check_row(c, "V1b linhas por versão (jan: 2, jul: 1)",
                    "select count(*) filter (where valid_from = '2026-01-01'), "
                    "count(*) filter (where valid_from = '2026-07-01') "
                    "from public.contract_revenue_splits where contract_id = $1", (2, 1), v1)

    async def version_sum_50():
        await c.execute("insert into public.contract_revenue_splits (contract_id, valid_from, share_kind, team_id, "
                        "scope, percentage) values ($1, '2026-03-01', 'dono', $2, 'g', 50)", v1, team_a)
        await c.execute("set constraints all immediate")
    await expect_fail(c, "V2 soma 100 é por versão (versão de março com 50 é barrada)", version_sum_50, "23514")
    await c.execute("set constraints all deferred")

    rt = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", split="2026-01-01")
    await expect_ok(c, "V3 setup: gera 12 parcelas com versão de jan/2026", lambda: gen(rt))
    await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                    "where contract_id = $1 and due_date = '2026-08-10'", rt)
    p_b = splits(("dono", team_b, "gerenciamento", 100))
    await expect_fail(c, "V3b versão de jul/2026 recusada: reatribuiria parcela emitida em ago",
                      lambda: set_split_imm(fin, rt, "2026-07-01", p_b), "55000")
    await expect_ok(c, "V3c a mesma versão passa com p_allow_retroactive = true",
                    lambda: set_split_imm(fin, rt, "2026-07-01", p_b, True))
    await expect_ok(c, "V3d versão de set/2026 passa: a emitida de ago fica fora da janela",
                    lambda: set_split_imm(fin, rt, "2026-09-01", p_b))
    await c.execute("update public.contract_installments set status = 'recebida', received_date = due_date, "
                    "received_amount = expected_amount where contract_id = $1 and due_date = '2026-10-10'", rt)
    await expect_fail(c, "V3e regravar set/2026 igual é recusado: recebida em out na janela (checagem conservadora)",
                      lambda: set_split_imm(fin, rt, "2026-09-01", p_b), "55000")
    await expect_fail(c, "V4 remover jul/2026 é recusado: a janela (jul a ago) tem a emitida de ago",
                      lambda: set_split_imm(fin, rt, "2026-07-01", "[]"), "55000")
    await expect_ok(c, "V4b remover jul/2026 com p_allow_retroactive passa (jan/2026 continua cobrindo)",
                    lambda: set_split_imm(fin, rt, "2026-07-01", "[]", True))
    await expect_fail(c, "V4c remover jan/2026, mesmo com retroativo, deixaria parcelas de jan a ago sem regra",
                      lambda: set_split_imm(fin, rt, "2026-01-01", "[]", True), "55000")
    ov = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_ok(c, "V4d setup: gera parcelas com a única versão (jan/2025)", lambda: gen(ov))
    await expect_fail(c, "V4e remover a única versão de contrato com parcelas é recusado",
                      lambda: set_split_imm(fin, ov, "2025-01-01", "[]", True), "55000")
    n = await expect_ok(c, "V5 remover versão que não existe", lambda: set_split_imm(fin, ov, "2030-01-01", "[]"))
    record("V5b devolve 0", n == 0, f"veio {n!r}")
    await expect_fail(c, "V6 valid_from fora do dia 1 recusado",
                      lambda: set_split_imm(fin, ov, "2026-01-15", splits(("dono", team_a, "g", 100))), "22023")

    async def allow_null():
        await as_user(c, fin)
        await c.fetchval("select public.set_contract_splits($1, '2026-01-01', '[]'::jsonb, null)", ov)
    await expect_fail(c, "V6b p_allow_retroactive nulo recusado", allow_null, "22004")

    async def splits_without_sub():
        await as_authenticated_no_sub(c)
        await c.fetchval(SPLITS, ov, "2026-01-01", "[]", None)
    await expect_fail(c, "V6c set_contract_splits sem auth.uid() recusado", splits_without_sub, "42501")

    g1 = await contract("parcela_unica", 1000, "2026-01-01", "2026-02-10", split=None)
    await expect_fail(c, "V7 generate sem nenhuma versão de regra recusado", lambda: gen(g1), "55000")
    g2 = await contract("parcela_unica", 1000, "2026-01-01", "2026-02-10", split="2026-03-01")
    await expect_fail(c, "V7b generate com versão só a partir de mar e 1º vencimento em fev recusado",
                      lambda: gen(g2), "55000")
    g3 = await contract("parcela_unica", 1000, "2026-01-01", "2026-02-10", split="2026-02-01")
    await expect_ok(c, "V7c generate com versão a partir do mês do 1º vencimento passa", lambda: gen(g3))

    e1 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_ok(c, "V8 setup: gera 12 parcelas", lambda: gen(e1))
    await c.execute("delete from public.contract_revenue_splits where contract_id = $1", e1)
    await expect_fail(c, "V8b extend sem regra vigente para a 1ª parcela nova recusado",
                      lambda: run_as(fin, EXT, e1), "55000")
    e2 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")

    async def gen_and_extend():
        await gen(e2)
        await run_as(fin, EXT, e2)
    await expect_ok(c, "V8c setup: gera e estende até o horizonte", gen_and_extend)
    await c.execute("delete from public.contract_revenue_splits where contract_id = $1", e2)
    n = await expect_ok(c, "V8d extend sem regra mas sem nada a criar", lambda: run_as(fin, EXT, e2))
    record("V8e devolve 0 sem erro (idempotência preservada)", n == 0, f"veio {n!r}")

    await check(c, "V9 competencia_month = mês do vencimento em todas as parcelas do teste",
                "select count(*) from public.contract_installments "
                "where competencia_month <> date_trunc('month', due_date::timestamp)::date", 0)


async def post_check(dsn, close_deal_before, genext_before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 contract_revenue_splits.valid_from ausente",
                        "select count(*) from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contract_revenue_splits' and column_name = 'valid_from'", 0)
            await check(c2, "L2 set_contract_splits da 045 de volta e a da 047 ausente",
                        "select to_regprocedure($1::text) is not null and to_regprocedure($2::text) is null",
                        True, OLD_SPLITS, NEW_SPLITS)
            await check(c2, "L3 unicidade dos splits de volta sem valid_from",
                        "select pg_get_constraintdef(oid) not like '%valid_from%' from pg_constraint "
                        "where conname = 'contract_revenue_splits_unique'", True)
            await check(c2, "L4 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            await check(c2, "L5 close_deal igual ao de antes do teste", CLOSE_DEAL_MD5_SQL, close_deal_before)
            await check(c2, "L6 nenhum projeto, time ou transação de teste",
                        "select (select count(*) from public.projects where name like 'TESTE 047%') + "
                        "(select count(*) from public.teams where name like 'TESTE 047%') + "
                        "(select count(*) from public.bank_transactions where external_id like 'teste047-%')", 0)
            await check(c2, "L7 generate/extend com o mesmo corpo da 046 de antes do teste",
                        GEN_EXT_MD5_SQL, genext_before)
    finally:
        await c2.close()


async def main():
    dsn = read_dsn()
    sql = MIGRATION.read_text(encoding="utf-8")
    c = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    tr = c.transaction()
    started = False
    try:
        close_deal_before, genext_before = await preconditions(c)
        await tr.start()
        started = True
        await run_tests(c, sql, close_deal_before)
    finally:
        if started:
            await tr.rollback()
            print("\nTransação DESFEITA (rollback).")
        await c.close()

    await post_check(dsn, close_deal_before, genext_before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
