"""Teste da migration 053 em PRODUÇÃO (que já tem da 043 à 052 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_053_prod.py

A 053 é aplicada dentro da transação e, sobre ela, rodam: A (estrutura),
I (INSERT), K (check de não-negativo), M (master em item de outro usuário com
relatório 'enviado'), O (master no próprio relatório), S (relatório fora de
'enviado'), N (quem não é master), E (regressão) e T (soma do valor aprovado).

RLS x gatilho: quando nenhuma policy de UPDATE libera a linha, o UPDATE não dá
erro, só afeta 0 linhas; esses casos (O1, S1, S2, N2, N3, E4) conferem
"UPDATE 0" e approved_amount intacto. O 42501 do gatilho aparece quando a RLS
libera a linha mas o conteúdo não é permitido (I2, I3, M6, M7, O2, N1).

Regras:
- Só roda com DATABASE_URL de backend/.env com sa-east-1 e a ref de
  produção, sem a ref de staging (checado antes de qualquer conexão).
- O e-mail do master vem de MASTER_EMAIL em backend/.env (lido junto com o
  DSN, antes de qualquer conexão; aborta se faltar). Não fica no código e
  não é impresso.
- Aborta, antes de abrir a transação de teste, se server_version_num < 150000,
  se a 052 não estiver aplicada (reimbursement_items.receipt_path ou
  fn_reimbursement_items_validate_total ausente), se a 053 já estiver
  (approved_amount, a função de guarda ou a policy nova existe), se o número
  de masters for diferente de 1 ou se esse master não for a conta do Diego
  (resolvida pelo MASTER_EMAIL).
- Dados reais: ANTES de qualquer teste (logo depois de abrir a transação)
  mede contagem + md5 (linha inteira) de 26 tabelas: auth.users, profiles,
  teams, profile_modules, team_members, contracts (sem billing_entity_id),
  proposals, billing_entities, clients, projects, service_types,
  contract_installments, contract_revenue_splits, bank_transactions,
  taxpayer_profiles, billing_contacts, contract_fiscal_settings,
  company_tax_regimes, dre_tax_rates, reimbursement_reports,
  reimbursement_items (sem approved_amount e approval_note),
  reimbursement_rate_rules, expense_categories, allocation_rules,
  allocation_rule_splits e team_cost_allocations (guardando as chaves), e
  o md5 do perfil + módulos do Diego. No fim da transação compara as linhas
  reais pelas chaves e confere que as linhas a mais são só de teste (a 053
  não cria linha em tabela existente); na conexão nova compara tudo
  inteiro. Nenhuma contagem real escrita no código.
  O master de teste criado dentro da transação não conta no DR4 (só os
  perfis reais medidos antes).
  ATENÇÃO: o md5 de auth.users usa a linha inteira; um login real durante o
  teste (last_sign_in_at) faz DR1/L8 de auth_users falharem sem defeito na 053.
- Aplica a 053 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint desfeito são
  desfeitos junto com ele.
- Itens de teste do tipo 'outros' (total = other_amount, sem depender de taxa).
- Usuários fictícios @example.invalid; nada de e-mail, senha, chave ou DSN
  impresso. Nenhum commit.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 127 verificações
  45 do teste de staging (abaixo)
  + 54 de dados reais no fim da transação:
    DR1 linhas reais intactas pelas chaves (26 tabelas) + DR2 Diego
    + DR3 linhas a mais só de teste (26 tabelas) + DR4 masters reais só o Diego
  + 28 de dados reais na conexão nova:
    L8 tabela inteira igual ao começo (26 tabelas) + L9 Diego + L10 master
  45 + 54 + 28 = 127
Detalhe dos 45:
  M0 1                                                                  -> 1
  + (a) A1 a A5 5, A6 x 2 papéis 2, A7, A8, A9 3                        -> 10
  + (i) I1 a I3                                                         -> 3
  + (k) K1 a K3                                                         -> 3
  + (m) M1 a M7                                                         -> 7
  + (o) O1, O2                                                          -> 2
  + (s) S1, S2                                                          -> 2
  + (n) N1 a N3                                                         -> 3
  + (e) E1 a E5                                                         -> 5
  + (t) T1, T2                                                          -> 2
  + pós-rollback L1 a L7                                                -> 7
  1 + 10 + 3 + 3 + 7 + 2 + 2 + 3 + 5 + 2 + 7 = 45
Se a M0 falhar: M0 + 54 + L1 a L7 + 28 = 90 verificações.
"""
import asyncio
import json
import secrets
import sys
from pathlib import Path

import asyncpg

import _lib

REPO = Path(r"C:\Users\pmon_admin\Documents\gestao-obras")
ENV_FILE = REPO / "backend" / ".env"
MASTER_EMAIL = None  # preenchido por read_dsn() com MASTER_EMAIL de backend/.env
# (chave, tabela, expressão da linha, coluna-chave, tipo da chave)
REAL_TABLES = [("auth_users", "auth.users", "to_jsonb(x)", "id", "uuid"),
               ("profiles", "public.profiles", "to_jsonb(x)", "id", "uuid"),
               ("teams", "public.teams", "to_jsonb(x)", "id", "uuid"),
               ("profile_modules", "public.profile_modules", "to_jsonb(x)", "id", "uuid"),
               ("team_members", "public.team_members", "to_jsonb(x)", "id", "uuid"),
               ("contracts", "public.contracts", "(to_jsonb(x) - 'billing_entity_id')", "id", "uuid"),
               ("proposals", "public.proposals", "to_jsonb(x)", "id", "uuid"),
               ("billing_entities", "public.billing_entities", "to_jsonb(x)", "id", "uuid"),
               ("clients", "public.clients", "to_jsonb(x)", "id", "uuid"),
               ("projects", "public.projects", "to_jsonb(x)", "id", "uuid"),
               ("service_types", "public.service_types", "to_jsonb(x)", "id", "uuid"),
               ("contract_installments", "public.contract_installments", "to_jsonb(x)", "id", "uuid"),
               ("contract_revenue_splits", "public.contract_revenue_splits", "to_jsonb(x)", "id", "uuid"),
               ("bank_transactions", "public.bank_transactions", "to_jsonb(x)", "id", "uuid"),
               ("taxpayer_profiles", "public.taxpayer_profiles", "to_jsonb(x)", "id", "uuid"),
               ("billing_contacts", "public.billing_contacts", "to_jsonb(x)", "id", "uuid"),
               ("contract_fiscal_settings", "public.contract_fiscal_settings", "to_jsonb(x)", "id", "uuid"),
               ("company_tax_regimes", "public.company_tax_regimes", "to_jsonb(x)", "valid_from", "date"),
               ("dre_tax_rates", "public.dre_tax_rates", "to_jsonb(x)", "month", "date"),
               ("reimbursement_reports", "public.reimbursement_reports", "to_jsonb(x)", "id", "uuid"),
               ("reimbursement_items", "public.reimbursement_items",
                "(to_jsonb(x) - 'approved_amount' - 'approval_note')", "id", "uuid"),
               ("reimbursement_rate_rules", "public.reimbursement_rate_rules", "to_jsonb(x)", "id", "uuid"),
               ("expense_categories", "public.expense_categories", "to_jsonb(x)", "id", "uuid"),
               ("allocation_rules", "public.allocation_rules", "to_jsonb(x)", "id", "uuid"),
               ("allocation_rule_splits", "public.allocation_rule_splits", "to_jsonb(x)", "id", "uuid"),
               ("team_cost_allocations", "public.team_cost_allocations", "to_jsonb(x)", "id", "uuid")]
MIGRATION = REPO / "backend" / "migrations" / "053_reimbursement_approved_amount.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste053-" + secrets.token_hex(4)
GUARD_FN = "public.fn_reimbursement_items_guard_approved_amount()"
NEW_POLICY = "reimbursement_items_approve_amount"
CHECK_NAME = "reimbursement_items_approved_amount_nonneg"
POLICIES_SQL = ("select md5(coalesce(string_agg(tablename::text || ':' || policyname::text || ':' || cmd::text || ':' "
                "|| coalesce(qual, '') || ':' || coalesce(with_check, ''), '|' order by tablename, policyname), '')) "
                "from pg_policies where schemaname = 'public' "
                "and tablename in ('reimbursement_items', 'reimbursement_reports') and policyname <> $1::text")
REPORTS_POLICIES_SQL = ("select md5(coalesce(string_agg(policyname::text || ':' || cmd::text || ':' || coalesce(qual, '') "
                        "|| ':' || coalesce(with_check, ''), '|' order by policyname), '')) from pg_policies "
                        "where schemaname = 'public' and tablename = 'reimbursement_reports'")
TRIGGERS_SQL = ("select string_agg(tgname::text, ',' order by tgname) from pg_trigger "
                "where tgrelid = 'public.reimbursement_items'::regclass and not tgisinternal")
ITEMS_FP_SQL = ("select count(*), md5(coalesce(string_agg(to_jsonb(x)::text, ',' order by x.id), '')) "
                "from public.reimbursement_items x")
INS_ITEM = ("insert into public.reimbursement_items (report_id, type, cost_center_id, expense_date, description, "
            "other_amount, total_amount, approved_amount, approval_note) values ($1, 'outros', $2, '2001-06-01', "
            "$3::text, ($4::text)::numeric, ($4::text)::numeric, ($5::text)::numeric, $6::text)")
SET_APPR = "update public.reimbursement_items set approved_amount = ($2::text)::numeric where id = $1"
SET_NOTE = "update public.reimbursement_items set approval_note = $2::text where id = $1"
SET_BOTH = ("update public.reimbursement_items set approved_amount = ($2::text)::numeric, approval_note = $3::text "
            "where id = $1")
SET_DESC = "update public.reimbursement_items set description = 'alterado 053' where id = $1"
SET_APPR_DESC = ("update public.reimbursement_items set approved_amount = 7, description = 'alterado 053' "
                 "where id = $1")
APPROVE = ("update public.reimbursement_reports set status = 'aprovado', approved_by = $2, approved_at = now() "
           "where id = $1")
APPR_OF = "select approved_amount from public.reimbursement_items where id = $1"
GUARD_MSG = "na aprovação do item só podem mudar"

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
    if "sa-east-1" not in dsn:
        abort("DATABASE_URL de backend/.env não é sa-east-1")
    if PROD_REF not in dsn:
        abort("DATABASE_URL não contém a ref de produção")
    if STAGING_REF in dsn:
        abort("DATABASE_URL contém a ref de STAGING")
    global MASTER_EMAIL
    MASTER_EMAIL = vals.get("MASTER_EMAIL", "")
    if "@" not in MASTER_EMAIL:
        abort("MASTER_EMAIL ausente ou inválido em backend/.env")
    return dsn


# ---------- papéis (SET LOCAL, dentro da transação) ----------
async def as_user(c, uid):
    await c.execute("set local role authenticated")
    await c.fetchval("select set_config('request.jwt.claim.sub', $1::text, true), "
                     "set_config('request.jwt.claims', $2::text, true)",
                     str(uid), json.dumps({"sub": str(uid), "role": "authenticated"}))


async def as_owner(c):
    await c.execute("reset role")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', '', true)")


# ---------- helpers de teste ----------
async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


async def check_row(c, name, sql, expected, *args):
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


async def expect_fail(c, name, fn, sqlstate, contains=None):
    """`contains`: trecho que a mensagem do erro precisa ter (gatilho e RLS dão
    os dois 42501)."""
    try:
        async with c.transaction():
            await fn()
        record(name, False, "não falhou")
    except asyncpg.PostgresError as e:
        msg = str(e)
        ok = e.sqlstate == sqlstate and (contains is None or contains in msg)
        record(name, ok, f"sqlstate {e.sqlstate} ({msg[:150]}), esperado {sqlstate}"
                         f"{' com ' + repr(contains) if contains else ''}")


async def status_of(c, fn):
    """fn num savepoint, sem registrar: devolve o resultado ou 'ERRO <sqlstate>: ...'."""
    try:
        async with c.transaction():
            return await fn()
    except asyncpg.PostgresError as e:
        return f"ERRO {e.sqlstate}: {str(e)[:150]}"


async def make_user(c, label):
    uid = await c.fetchval(
        "insert into auth.users (id, aud, role, email, created_at, updated_at) "
        "values (gen_random_uuid(), 'authenticated', 'authenticated', $1::text, now(), now()) returning id",
        f"{TAG}-{label}@example.invalid")
    if not await c.fetchval("select exists (select 1 from public.profiles where id = $1)", uid):
        await c.execute("insert into public.profiles (id) values ($1)", uid)
    return uid


# ---------- pré-condições (fora da transação, só leitura) ----------
async def preconditions(c):
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
    rows = await c.fetch("select id from auth.users where lower(email) = lower($1::text)", MASTER_EMAIL)
    if len(rows) != 1:
        abort(f"esperada 1 conta com o MASTER_EMAIL, achou {len(rows)}")
    diego = rows[0]["id"]
    masters = await master_ids(c)
    print(f"masters em profiles: {len(masters)}")
    if len(masters) != 1:
        abort(f"esperado exatamente 1 master, achou {len(masters)}")
    if masters[0] != diego:
        abort("o master existente não é a conta do Diego (resolvida pelo MASTER_EMAIL)")
    print("master existente = conta do Diego (resolvida pelo MASTER_EMAIL)")
    print(f"itens antes da 053: {await c.fetchval('select count(*) from public.reimbursement_items')}")
    return {"policies": await c.fetchval(POLICIES_SQL, NEW_POLICY),
            "reports_policies": await c.fetchval(REPORTS_POLICIES_SQL),
            "triggers": await c.fetchval(TRIGGERS_SQL),
            "items_fp": tuple(await c.fetchrow(ITEMS_FP_SQL)),
            "diego": diego}


# ---------- dados reais: contagem + md5 ----------
async def master_ids(c, among=None):
    if among is None:
        return [r["id"] for r in await c.fetch("select id from public.profiles where system_role = 'master'")]
    return [r["id"] for r in await c.fetch(
        "select id from public.profiles where system_role = 'master' and id = any($1::uuid[])", among)]


async def table_fp(c, table, expr, key, ktype, keys=None):
    """(contagem, md5) da tabela pela expressão json da linha; com keys, só dessas linhas."""
    where = f"where x.{key} = any($1::{ktype}[])" if keys is not None else ""
    row = await c.fetchrow(
        f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.{key}), '')) as h "
        f"from {table} x {where}", *([keys] if keys is not None else []))
    return row["n"], row["h"]


async def diego_fp(c, diego):
    return await c.fetchval(
        "select md5(coalesce((select row_to_json(p)::text from public.profiles p where p.id = $1), '') || '|' || "
        "coalesce((select string_agg(module, ',' order by module) from public.profile_modules "
        "where profile_id = $1), ''))", diego)


def fmt(fp):
    return f"{fp[0]} (md5 {fp[1][:12]}…)"


async def measure_before(c, diego):
    keys, fp = {}, {}
    for name, table, expr, key, ktype in REAL_TABLES:
        keys[name] = [r[key] for r in await c.fetch(f"select {key} from {table}")]
        fp[name] = await table_fp(c, table, expr, key, ktype)
    fp["diego"] = await diego_fp(c, diego)
    print("dados reais antes: " + ", ".join(f"{n}={fmt(fp[n])}" for n, _, _, _, _ in REAL_TABLES)
          + f"; Diego md5 {fp['diego'][:12]}…")
    return keys, fp


async def real_data_in_txn(c, keys, fp_before, diego):
    """Ainda dentro da transação: linhas reais pelas chaves guardadas; as linhas
    a mais só podem ser de teste (ligadas à TAG desta execução). A 053 não cria
    linha em tabela existente."""
    print("\n== dados reais (fim da transação) ==")
    for name, table, expr, key, ktype in REAL_TABLES:
        now = await table_fp(c, table, expr, key, ktype, keys[name])
        b = fp_before[name]
        record(f"DR1 {name}: linhas reais intactas (contagem + md5 pelas chaves)", now == b,
               f"antes {fmt(b)}, agora {fmt(now)}")
    record("DR2 perfil e módulos do Diego intactos (md5)", await diego_fp(c, diego) == fp_before["diego"])

    test_users = f"(select id from auth.users where email like '{TAG}-%@example.invalid')"
    test_projects = f"(select id from public.projects where name like '%{TAG}')"
    test_clients = (f"(select client_id from public.projects where name like '%{TAG}' "
                    f"and client_id is not null)")
    test_contracts = f"(select id from public.contracts where project_id in {test_projects})"
    test_spes = f"(select id from public.billing_entities where project_id in {test_projects})"
    test_reports = f"(select id from public.reimbursement_reports where profile_id in {test_users})"
    only_real = {
        "auth_users": f"and email not like '{TAG}-%@example.invalid'",
        "profiles": f"and id not in {test_users}",
        "teams": f"and name not like '%{TAG}'",
        "profile_modules": f"and profile_id not in {test_users}",
        "team_members": f"and profile_id not in {test_users}",
        "contracts": f"and project_id not in {test_projects}",
        "proposals": f"and project_id not in {test_projects}",
        "billing_entities": f"and project_id not in {test_projects}",
        "clients": f"and id not in {test_clients}",
        "projects": f"and name not like '%{TAG}'",
        "service_types": "",
        "contract_installments": f"and contract_id not in {test_contracts}",
        "contract_revenue_splits": f"and contract_id not in {test_contracts}",
        "bank_transactions": "",
        "taxpayer_profiles": f"and billing_entity_id not in {test_spes}",
        "billing_contacts": "",
        "contract_fiscal_settings": f"and contract_id not in {test_contracts}",
        "company_tax_regimes": "",
        "dre_tax_rates": "",
        "reimbursement_reports": f"and profile_id not in {test_users}",
        "reimbursement_items": f"and report_id not in {test_reports}",
        "reimbursement_rate_rules": f"and notes is distinct from '{TAG}'",
        "expense_categories": "",
        "allocation_rules": "",
        "allocation_rule_splits": "",
        "team_cost_allocations": "",
    }
    for name, table, _, key, ktype in REAL_TABLES:
        await check(c, f"DR3 {name}: linhas a mais são só de teste",
                    f"select count(*) from {table} where {key} <> all($1::{ktype}[]) {only_real[name]}",
                    0, keys[name])
    # o master real continua sendo só o Diego entre os perfis reais (o master de teste não entra)
    m = await master_ids(c, keys["profiles"])
    record("DR4 masters entre os perfis reais = só o Diego", m == [diego], f"{len(m)} master(s) real(is)")


async def run_tests(c, sql, before):
    cat = await c.fetchval("select id from public.expense_categories order by name limit 1")
    D = f"TESTE 053 {TAG}"

    async def report(owner, status):
        return await c.fetchval(
            "insert into public.reimbursement_reports (profile_id, period_start, period_end, status) "
            "values ($1, '2001-01-01', '2001-12-31', $2::text) returning id", owner, status)

    async def item(rep, amount="10.00"):
        """Item 'outros' válido, sem valor aprovado, gravado pelo dono da conexão."""
        return await c.fetchval(INS_ITEM + " returning id", rep, cat, D, amount, None, None)

    async def run_as(uid, q, *args, fetch=False):
        # sem try/finally: num savepoint que falha, o rollback dele já desfaz o papel
        await as_user(c, uid)
        r = await (c.fetchval(q, *args) if fetch else c.execute(q, *args))
        await as_owner(c)
        return r

    def do(uid, q, *args, expect=None):
        async def f():
            st = await run_as(uid, q, *args)
            if expect is not None:
                assert st == expect, f"esperado {expect!r}, veio {st!r}"
            return st
        return f

    def own(q, *args, expect=None):
        async def f():
            st = await c.execute(q, *args)
            if expect is not None:
                assert st == expect, f"esperado {expect!r}, veio {st!r}"
            return st
        return f

    async def no_change(label, uid, item_id):
        """RLS não libera a linha: 0 linhas e approved_amount continua nulo."""
        st = await status_of(c, do(uid, SET_APPR, item_id, "1.23"))
        v = await c.fetchval(APPR_OF, item_id)
        record(label, st == "UPDATE 0" and v is None, f"{st}; approved_amount {v!r}")

    # ---------- dados de apoio (dono da conexão) ----------
    owner_u = await make_user(c, "dono")
    fin = await make_user(c, "fin")
    master = await make_user(c, "master")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro')", fin)
    # system_role só muda com auth.uid() nulo (043): aqui, sem usuário logado
    await c.execute("update public.profiles set system_role = 'master' where id = $1", master)

    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 053 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 053 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # ---------- (a) estrutura ----------
    COL = ("select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
           "where table_schema = 'public' and table_name = 'reimbursement_items' and column_name = $1::text")
    await check_row(c, "A1 approved_amount: numeric, aceita nulo, sem padrão", COL, ("numeric", "YES", None),
                    "approved_amount")
    await check_row(c, "A2 approval_note: text, aceita nulo, sem padrão", COL, ("text", "YES", None), "approval_note")
    await check(c, "A3 check de não-negativo em approved_amount",
                "select count(*) from pg_constraint where conrelid = 'public.reimbursement_items'::regclass "
                "and conname = $1::text and contype = 'c' and pg_get_constraintdef(oid) like '%approved_amount >= %'",
                1, CHECK_NAME)
    # tgtype 23 = ROW (1) + BEFORE (2) + INSERT (4) + UPDATE (16); sem UPDATE OF
    await check(c, "A4 trg_reimbursement_items_guard_approved_amount: BEFORE INSERT OR UPDATE (todo UPDATE), ligado",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_items_guard_approved_amount' "
                "and tgrelid = 'public.reimbursement_items'::regclass and tgtype = 23 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text) and pg_get_triggerdef(oid) not like '%UPDATE OF%'",
                1, GUARD_FN)
    await check(c, "A5 função de guarda: security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, GUARD_FN)
    for role in ("anon", "authenticated"):
        await check(c, f"A6 {role} sem EXECUTE na função de guarda",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, GUARD_FN)
    await check(c, "A7 PUBLIC sem EXECUTE na função de guarda",
                "select not exists (select 1 from pg_proc p, aclexplode(p.proacl) a "
                "where p.oid = to_regprocedure($1::text) and a.grantee = 0 and a.privilege_type = 'EXECUTE')",
                True, GUARD_FN)
    await check(c, "A8 policy reimbursement_items_approve_amount: UPDATE, master, 'enviado', não o próprio",
                "select cmd = 'UPDATE' and qual like '%is_master()%' and qual like '%enviado%' "
                "and qual like '%profile_id <> auth.uid()%' and with_check like '%is_master()%' "
                "and with_check like '%profile_id <> auth.uid()%' from pg_policies where schemaname = 'public' "
                "and tablename = 'reimbursement_items' and policyname = $1::text", True, NEW_POLICY)
    await check(c, "A9 as demais policies de itens e relatórios iguais às de antes", POLICIES_SQL,
                before["policies"], NEW_POLICY)

    # ---------- dados de apoio, depois da 053 ----------
    r_rasc = await report(owner_u, "rascunho")
    r_env = await report(owner_u, "enviado")
    r_apr = await report(owner_u, "aprovado")
    r_mine_env = await report(master, "enviado")
    r_mine_rasc = await report(master, "rascunho")

    # ---------- (i) INSERT ----------
    await expect_ok(c, "I1 dono cria item com approved_amount e approval_note nulos",
                    do(owner_u, INS_ITEM, r_rasc, cat, D, "10.00", None, None, expect="INSERT 0 1"))
    await expect_fail(c, "I2 dono cria item com approved_amount preenchido: recusado",
                      do(owner_u, INS_ITEM, r_rasc, cat, D, "10.00", "10.00", None), "42501", "não podem vir preenchidos")
    await expect_fail(c, "I3 dono cria item com approval_note preenchida: recusado",
                      do(owner_u, INS_ITEM, r_rasc, cat, D, "10.00", None, "nota"), "42501", "não podem vir preenchidos")

    # ---------- (k) check de não-negativo (dono da conexão: o gatilho não se aplica) ----------
    i_k = await item(r_env)
    await expect_fail(c, "K1 approved_amount negativo recusado pelo check", own(SET_APPR, i_k, "-1"), "23514", CHECK_NAME)
    await expect_ok(c, "K2 approved_amount zero aceito", own(SET_APPR, i_k, "0", expect="UPDATE 1"))
    await expect_ok(c, "K3 approved_amount nulo aceito", own(SET_APPR, i_k, None, expect="UPDATE 1"))

    # ---------- (m) master, item de outro usuário, relatório 'enviado' ----------
    i_m = await item(r_env, "10.00")
    await expect_ok(c, "M1 master grava só approved_amount", do(master, SET_APPR, i_m, "8.00", expect="UPDATE 1"))
    await expect_ok(c, "M2 master grava só approval_note", do(master, SET_NOTE, i_m, "glosa parcial", expect="UPDATE 1"))
    await expect_ok(c, "M3 master grava os dois juntos",
                    do(master, SET_BOTH, i_m, "9.00", "ajuste", expect="UPDATE 1"))
    await expect_ok(c, "M4 master aprova acima do pedido (15,00 > 10,00)", do(master, SET_APPR, i_m, "15.00",
                                                                              expect="UPDATE 1"))
    await expect_ok(c, "M5 master glosa total (approved_amount = 0)", do(master, SET_APPR, i_m, "0", expect="UPDATE 1"))
    i_m6 = await item(r_env)
    await expect_fail(c, "M6 master muda approved_amount e description juntos: recusado (brecha 1 fechada)",
                      do(master, SET_APPR_DESC, i_m6), "42501", GUARD_MSG)
    await expect_fail(c, "M7 master muda só description: recusado",
                      do(master, SET_DESC, i_m6), "42501", GUARD_MSG)

    # ---------- (o) master no próprio relatório ----------
    i_mine_env = await item(r_mine_env)
    await no_change("O1 master, próprio relatório em 'enviado': nenhuma policy libera (0 linhas, intacto)",
                    master, i_mine_env)
    i_mine_rasc = await item(r_mine_rasc)
    await expect_fail(c, "O2 master, próprio relatório em rascunho (RLS do dono libera): gatilho recusa",
                      do(master, SET_APPR, i_mine_rasc, "5.00"), "42501", "próprio relatório")

    # ---------- (s) relatório de outro usuário fora de 'enviado' ----------
    await no_change("S1 master, relatório em rascunho: 0 linhas, intacto", master, await item(r_rasc))
    await no_change("S2 master, relatório aprovado: 0 linhas, intacto", master, await item(r_apr))

    # ---------- (n) quem não é master ----------
    await expect_fail(c, "N1 dono, próprio item em rascunho (RLS libera): gatilho recusa",
                      do(owner_u, SET_APPR, await item(r_rasc), "5.00"), "42501", "só podem ser alterados pelo master")
    await no_change("N2 dono, próprio item em 'enviado': 0 linhas, intacto", owner_u, await item(r_env))
    await no_change("N3 financeiro, item de outro em 'enviado': 0 linhas, intacto", fin, await item(r_env))

    # ---------- (e) regressão ----------
    i_e1 = await item(r_rasc)

    async def edit_desc():
        st = await run_as(owner_u, SET_DESC, i_e1)
        assert st == "UPDATE 1", f"esperado 'UPDATE 1', veio {st!r}"
        v = await c.fetchval("select description from public.reimbursement_items where id = $1", i_e1)
        assert v == "alterado 053", f"description veio {v!r}"
    await expect_ok(c, "E1 dono edita description do próprio item em rascunho (fluxo existente)", edit_desc)

    async def e2e():
        """Fluxo do app: criar relatório, lançar item, enviar, master ajusta o valor e aprova."""
        rid = await run_as(owner_u, "insert into public.reimbursement_reports (profile_id, period_start, period_end, "
                                    "status) values ($1, '2001-01-01', '2001-12-31', 'rascunho') returning id",
                           owner_u, fetch=True)
        iid = await run_as(owner_u, "insert into public.reimbursement_items (report_id, type, cost_center_id, "
                                    "expense_date, description, other_amount, total_amount) values ($1, 'outros', $2, "
                                    "'2001-06-01', $3::text, 20, 20) returning id", rid, cat, D, fetch=True)
        st = await run_as(owner_u, "update public.reimbursement_reports set status = 'enviado' where id = $1", rid)
        assert st == "UPDATE 1", f"enviar: {st!r}"
        st = await run_as(master, SET_APPR, iid, "12.00")
        assert st == "UPDATE 1", f"ajustar valor: {st!r}"
        st = await run_as(master, APPROVE, rid, master)
        assert st == "UPDATE 1", f"aprovar: {st!r}"
        return rid, iid

    got = await expect_ok(c, "E2 fluxo: rascunho -> item -> enviar -> master ajusta valor -> aprova", e2e)
    rid, iid = got if got else (None, None)
    await check_row(c, "E3 relatório do fluxo aprovado pelo master, item com approved_amount 12,00",
                    "select r.status, r.approved_by = $2, i.approved_amount from public.reimbursement_reports r "
                    "join public.reimbursement_items i on i.report_id = r.id where r.id = $1 and i.id = $3",
                    ("aprovado", True, 12), rid, master, iid)
    st = await status_of(c, do(master, SET_APPR, iid, "1.00"))
    v = await c.fetchval(APPR_OF, iid)
    record("E4 depois de aprovado, master não muda mais approved_amount (0 linhas, mantém 12,00)",
           st == "UPDATE 0" and v == 12, f"{st}; approved_amount {v!r}")
    await check(c, "E5 policies de reimbursement_reports iguais às de antes", REPORTS_POLICIES_SQL,
                before["reports_policies"])

    # ---------- (t) soma do valor aprovado (lógica em SQL; não há função/view ainda) ----------
    r_sum = await report(owner_u, "enviado")
    i_s1 = await item(r_sum, "10.00")
    await item(r_sum, "20.00")
    await status_of(c, do(master, SET_APPR, i_s1, "5.00"))  # se falhar, o T1 acusa
    await check(c, "T1 soma(coalesce(approved_amount, total_amount)) = 5,00 + 20,00 = 25,00",
                "select sum(coalesce(approved_amount, total_amount)) from public.reimbursement_items "
                "where report_id = $1", 25, r_sum)
    await check(c, "T2 soma do pedido (total_amount) continua 30,00",
                "select sum(total_amount) from public.reimbursement_items where report_id = $1", 30, r_sum)


async def post_check(dsn, before, fp_before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("prod"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 colunas approved_amount e approval_note ausentes",
                        "select count(*) from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'reimbursement_items' and column_name in ('approved_amount', 'approval_note')",
                        0)
            await check(c2, "L2 check de não-negativo ausente",
                        "select count(*) from pg_constraint where conname = $1::text", 0, CHECK_NAME)
            await check(c2, "L3 função de guarda ausente", "select to_regprocedure($1::text) is null", True, GUARD_FN)
            await check(c2, "L4 gatilhos de reimbursement_items iguais aos de antes", TRIGGERS_SQL, before["triggers"])
            await check(c2, "L5 policies de itens e relatórios iguais às de antes (e sem a policy nova)",
                        "select (" + POLICIES_SQL.replace("$1::text", "''") + ") = $1::text and not exists "
                        "(select 1 from pg_policies where schemaname = 'public' and policyname = $2::text)",
                        True, before["policies"], NEW_POLICY)
            await check(c2, "L6 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            record("L7 reimbursement_items igual ao de antes (contagem + md5)",
                   tuple(await c2.fetchrow(ITEMS_FP_SQL)) == before["items_fp"])
            diego = before["diego"]
            for name, table, expr, key, ktype in REAL_TABLES:
                now = await table_fp(c2, table, expr, key, ktype)
                b = fp_before[name]
                record(f"L8 {name}: tabela inteira igual ao começo (contagem + md5)", now == b,
                       f"antes {fmt(b)}, depois {fmt(now)}")
            record("L9 perfil e módulos do Diego iguais ao começo (md5)",
                   await diego_fp(c2, diego) == fp_before["diego"])
            m = await master_ids(c2)
            record("L10 masters = 1 e é o Diego", m == [diego], f"{len(m)} master(s)")
    finally:
        await c2.close()


async def main():
    dsn = read_dsn()
    sql = MIGRATION.read_text(encoding="utf-8")
    c = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("prod"))
    tr = c.transaction()
    started = False
    try:
        before = await preconditions(c)
        await tr.start()
        started = True
        keys, fp_before = await measure_before(c, before["diego"])
        await run_tests(c, sql, before)
        await real_data_in_txn(c, keys, fp_before, before["diego"])
    finally:
        if started:
            await tr.rollback()
            print("\nTransação DESFEITA (rollback).")
        await c.close()

    await post_check(dsn, before, fp_before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
