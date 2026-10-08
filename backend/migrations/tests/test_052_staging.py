"""Teste da migration 052 no STAGING (que já tem da 043 à 051 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_052_staging.py

Antes da 052, X0 mostra o furo (financeiro apaga item de relatório aprovado).
A 052 é aplicada dentro da transação e, sobre ela, rodam: A (estrutura:
policies, gatilhos, funções, privilégios), P (policies de reimbursement_items),
R (leitura pelo master sem módulo), G (aprovação e gatilho de guarda),
V (validação do total), C (coluna do comprovante), D (rateio padrão por time)
e E (regressão: fluxo de ponta a ponta e tabelas fora do escopo).

Regras:
- Só roda com DATABASE_URL de backend/.env.staging com us-west-2 e a ref de
  staging, sem a ref de produção (checado antes de qualquer conexão).
- Aborta, antes de abrir a transação de teste, se server_version_num < 150000,
  se a 051 não estiver aplicada (contracts.billing_entity_id ausente), se a 052
  já estiver (reimbursement_items.receipt_path, a regra 'Time Diego/Murillo
  100%' ou a função do gatilho de total existe) ou se o time 'Diego/Murillo'
  não existir.
- Aplica a 052 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint desfeito são
  desfeitos junto com ele. X0 roda num savepoint próprio, também desfeito.
- Taxas de teste em 2001 (sem sobrepor as taxas reais, que começam em 2026);
  a data sem taxa é 1990-01-01.
- Usuários fictícios @example.invalid, time fictício 'TESTE 052 ...'; nada de
  e-mail, senha, chave ou DSN impresso. Nenhum commit.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 79 verificações
  X0 1 (furo antes da 052) + M0 1                                       -> 2
  + (a) A1, A2, A3 3, A4 x 2 funções x 2 papéis 4, A5 x 3 funções 3,
        A6, A7 2                                                        -> 12
  + (p) P1 a P11 11, P12 x 3 status 3                                   -> 14
  + (r) R1 a R3                                                         -> 3
  + (g) G1 a G10                                                        -> 10
  + (v) V1 a V11                                                        -> 11
  + (c) C1 a C4                                                         -> 4
  + (d) D1 a D5 (laço de 5 perfis) 5 + D6 1                             -> 6
  + (e) E1, E2 2, E3 x 4 tabelas 4                                      -> 6
  + pós-rollback L1 a L11                                               -> 11
  2 + 12 + 14 + 3 + 10 + 11 + 4 + 6 + 6 + 11 = 79
Se a M0 falhar, o script para logo depois: X0 + M0 + L1 a L11 = 13 verificações.
"""
import asyncio
import json
import secrets
import sys
from pathlib import Path

import asyncpg

import _lib

REPO = Path(r"C:\Users\pmon_admin\Documents\gestao-obras")
ENV_FILE = REPO / "backend" / ".env.staging"
MIGRATION = REPO / "backend" / "migrations" / "052_reembolso_fixes.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste052-" + secrets.token_hex(4)
DM_RULE = "Time Diego/Murillo 100%"
GUARD_FN = "public.fn_reimbursement_reports_guard_approval()"
TOTAL_FN = "public.fn_reimbursement_items_validate_total()"
ALLOC_FN = "public.default_allocation_rule_for_profile(uuid)"
NEW_FUNC_NAMES = ["fn_reimbursement_reports_guard_approval", "fn_reimbursement_items_validate_total"]
OUT_OF_SCOPE = ["reimbursement_rate_rules", "expense_categories", "allocation_rules", "team_cost_allocations"]
POLICIES_SQL = ("select md5(coalesce(string_agg(tablename::text || ':' || policyname::text || ':' || cmd::text || ':' "
                "|| coalesce(qual, '') || ':' || coalesce(with_check, ''), '|' order by tablename, policyname), '')) "
                "from pg_policies where schemaname = 'public' "
                "and tablename in ('reimbursement_items', 'reimbursement_reports')")
TRIGGERS_SQL = ("select string_agg(tgrelid::regclass::text || '.' || tgname::text, ',' order by tgrelid::regclass::text, "
                "tgname) from pg_trigger where tgrelid in ('public.reimbursement_items'::regclass, "
                "'public.reimbursement_reports'::regclass) and not tgisinternal")
ALLOC_MD5_SQL = f"select md5(pg_get_functiondef(to_regprocedure('{ALLOC_FN}')))"
RATES_FP_SQL = ("select count(*), md5(coalesce(string_agg(to_jsonb(x)::text, ',' order by x.id), '')) "
                "from public.reimbursement_rate_rules x")
# colunas + policies + gatilhos de uma tabela fora do escopo da 052
TABLE_STRUCT_SQL = (
    "select md5("
    "coalesce((select string_agg(column_name::text || ':' || data_type::text || ':' || is_nullable::text || ':' || "
    "coalesce(column_default::text, ''), ',' order by ordinal_position) from information_schema.columns "
    "where table_schema = 'public' and table_name = $1::text), '') || '|' || "
    "coalesce((select string_agg(policyname::text || ':' || cmd::text || ':' || coalesce(qual, '') || ':' || "
    "coalesce(with_check, ''), ',' order by policyname) from pg_policies "
    "where schemaname = 'public' and tablename = $1::text), '') || '|' || "
    "coalesce((select string_agg(tgname::text, ',' order by tgname) from pg_trigger "
    "where tgrelid = to_regclass('public.' || $1::text) and not tgisinternal), ''))")
INS_ITEM = ("insert into public.reimbursement_items (report_id, type, project_id, cost_center_id, expense_date, "
            "description, km_traveled, km_rate, toll_amount, other_amount, total_amount) values ($1, $2::text, $3, $4, "
            "($5::text)::date, $6::text, ($7::text)::numeric, ($8::text)::numeric, ($9::text)::numeric, "
            "($10::text)::numeric, ($11::text)::numeric)")
APPROVE = ("update public.reimbursement_reports set status = 'aprovado', approved_by = $2, approved_at = now() "
           "where id = $1")
RLS = "row-level security"

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
    """`contains`: trecho que a mensagem do erro precisa ter (o gatilho de guarda
    e a RLS dão os dois 42501)."""
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
                            "and table_name = 'contracts' and column_name = 'billing_entity_id')"):
        abort("a 051 não está aplicada (contracts.billing_entity_id ausente)")
    if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'reimbursement_items' and column_name = 'receipt_path')"):
        abort("a 052 parece já aplicada (reimbursement_items.receipt_path existe)")
    if await c.fetchval("select exists (select 1 from public.allocation_rules where name = $1::text)", DM_RULE):
        abort(f"a 052 parece já aplicada (a regra '{DM_RULE}' existe)")
    if await c.fetchval("select to_regprocedure($1::text) is not null", TOTAL_FN):
        abort("a 052 parece já aplicada (fn_reimbursement_items_validate_total existe)")
    if not await c.fetchval("select exists (select 1 from public.teams where name = 'Diego/Murillo')"):
        abort("o time 'Diego/Murillo' não existe em staging: a 052 abortaria no item 6a")
    print(f"relatórios antes da 052: {await c.fetchval('select count(*) from public.reimbursement_reports')}; "
          f"itens: {await c.fetchval('select count(*) from public.reimbursement_items')}")
    return {"policies": await c.fetchval(POLICIES_SQL),
            "triggers": await c.fetchval(TRIGGERS_SQL),
            "alloc_md5": await c.fetchval(ALLOC_MD5_SQL),
            "rates_fp": tuple(await c.fetchrow(RATES_FP_SQL)),
            "struct": {t: await c.fetchval(TABLE_STRUCT_SQL, t) for t in OUT_OF_SCOPE}}


async def run_tests(c, sql, before):
    cat = await c.fetchval("select id from public.expense_categories order by name limit 1")

    async def report(owner, status, period=("2001-01-01", "2001-12-31")):
        return await c.fetchval(
            "insert into public.reimbursement_reports (profile_id, period_start, period_end, status) "
            "values ($1, ($2::text)::date, ($3::text)::date, $4::text) returning id", owner, *period, status)

    async def item_outros(rep, amount="10.00"):
        """Item 'outros' válido (total = other_amount), gravado pelo dono da conexão."""
        return await c.fetchval(INS_ITEM + " returning id", rep, "outros", None, cat, "2001-06-01",
                                f"TESTE 052 {TAG}", None, None, "0", amount, amount)

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

    async def exists_item(item_id):
        return await c.fetchval("select exists (select 1 from public.reimbursement_items where id = $1)", item_id)

    # ---------- dados de apoio (dono da conexão), antes da 052 ----------
    owner_u = await make_user(c, "dono")
    other_u = await make_user(c, "outro")
    fin = await make_user(c, "fin")
    master = await make_user(c, "master")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro')", fin)
    # system_role só muda com auth.uid() nulo (043): aqui, sem usuário logado
    await c.execute("update public.profiles set system_role = 'master' where id = $1", master)
    r_apr = await report(owner_u, "aprovado")
    i_apr = await item_outros(r_apr)

    # X0: o furo antes da 052 (savepoint próprio, sempre desfeito)
    DEL = "delete from public.reimbursement_items where id = $1"
    sp = c.transaction()
    await sp.start()
    st = await status_of(c, do(fin, DEL, i_apr))
    await sp.rollback()
    record("X0 antes da 052: financeiro apaga item de relatório APROVADO (o furo existe)",
           st == "DELETE 1" and await exists_item(i_apr), f"{st}; item ainda existe após desfazer: "
                                                            f"{await exists_item(i_apr)}")

    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 052 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 052 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # ---------- (a) estrutura ----------
    await check(c, "A1 reimbursement_items: só as 4 policies novas, uma por comando",
                "select string_agg(policyname::text || ':' || cmd::text, ',' order by policyname) from pg_policies "
                "where schemaname = 'public' and tablename = 'reimbursement_items'",
                "reimbursement_items_delete:DELETE,reimbursement_items_insert:INSERT,"
                "reimbursement_items_select:SELECT,reimbursement_items_update:UPDATE")
    # tgtype 19 = ROW (1) + BEFORE (2) + UPDATE (16); tgenabled 'O' = ligado
    await check(c, "A2 trg_reimbursement_reports_guard_approval: BEFORE UPDATE, por linha, ligado",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_reports_guard_approval' "
                "and tgrelid = 'public.reimbursement_reports'::regclass and tgtype = 19 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text)", 1, GUARD_FN)
    # tgtype 23 = ROW (1) + BEFORE (2) + INSERT (4) + UPDATE (16)
    await check(c, "A3 trg_reimbursement_items_validate_total: BEFORE INSERT OR UPDATE OF as colunas de valor",
                "select count(*) from pg_trigger where tgname = 'trg_reimbursement_items_validate_total' "
                "and tgrelid = 'public.reimbursement_items'::regclass and tgtype = 23 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text) and pg_get_triggerdef(oid) like '%UPDATE OF type, "
                "expense_date, km_traveled, km_rate, toll_amount, other_amount, total_amount ON "
                "public.reimbursement_items%'", 1, TOTAL_FN)
    for fn in (GUARD_FN, TOTAL_FN):
        for role in ("anon", "authenticated"):
            await check(c, f"A4 {role} sem EXECUTE em {fn}",
                        "select has_function_privilege($1::name, $2::text, 'execute')", False, role, fn)
    for fn in (GUARD_FN, TOTAL_FN, ALLOC_FN):
        await check(c, f"A5 {fn} com search_path vazio",
                    "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                    "from pg_proc where oid = to_regprocedure($1::text)", True, fn)
    await check(c, "A6 anon sem EXECUTE em default_allocation_rule_for_profile",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, ALLOC_FN)
    await check(c, "A7 authenticated com EXECUTE em default_allocation_rule_for_profile",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, ALLOC_FN)

    # ---------- dados de apoio, depois da 052 (itens 'outros' válidos) ----------
    r_rasc = await report(owner_u, "rascunho")
    r_env = await report(owner_u, "enviado")
    r_other = await report(other_u, "rascunho")
    i_own = await item_outros(r_rasc)
    i_del = await item_outros(r_rasc)
    i_env = await item_outros(r_env)
    COUNT_ITEM = "select count(*) from public.reimbursement_items where id = $1"
    UPD_DESC = "update public.reimbursement_items set description = 'alterado' where id = $1"

    # ---------- (p) policies de reimbursement_items ----------
    for label, uid, expected in (("P1 dono vê o próprio item", owner_u, 1),
                                 ("P2 outro usuário comum não vê", other_u, 0),
                                 ("P3 financeiro vê", fin, 1),
                                 ("P4 master sem módulo vê", master, 1)):
        n = await status_of(c, lambda uid=uid: run_as(uid, COUNT_ITEM, i_own, fetch=True))
        record(label, n == expected, f"esperado {expected}, veio {n}")
    await expect_ok(c, "P5 INSERT: dono em relatório próprio em rascunho",
                    do(owner_u, INS_ITEM, r_rasc, "outros", None, cat, "2001-06-01", f"TESTE 052 {TAG}",
                       None, None, "0", "5.00", "5.00", expect="INSERT 0 1"))
    await expect_fail(c, "P6 INSERT: dono em relatório de outro usuário recusado",
                      do(owner_u, INS_ITEM, r_other, "outros", None, cat, "2001-06-01", f"TESTE 052 {TAG}",
                         None, None, "0", "5.00", "5.00"), "42501", RLS)
    await expect_ok(c, "P7 UPDATE: dono em rascunho", do(owner_u, UPD_DESC, i_own, expect="UPDATE 1"))
    st = await status_of(c, do(owner_u, UPD_DESC, i_env))
    desc = await c.fetchval("select description from public.reimbursement_items where id = $1", i_env)
    record("P8 UPDATE: dono em relatório enviado não altera (0 linhas, valor mantido)",
           st == "UPDATE 0" and desc != "alterado", f"{st}; descrição: {desc!r}")
    st = await status_of(c, do(fin, UPD_DESC, i_del))
    record("P9 UPDATE: financeiro não altera mais (0 linhas)", st == "UPDATE 0", str(st))
    await expect_ok(c, "P10 DELETE: dono em rascunho", do(owner_u, DEL, i_del, expect="DELETE 1"))
    st = await status_of(c, do(owner_u, DEL, i_env))
    record("P11 DELETE: dono em relatório enviado não apaga (0 linhas, item mantido)",
           st == "DELETE 0" and await exists_item(i_env), f"{st}; item existe: {await exists_item(i_env)}")
    for status, item_id in (("rascunho", i_own), ("enviado", i_env), ("aprovado (o furo do X0)", i_apr)):
        st = await status_of(c, do(fin, DEL, item_id))
        record(f"P12 DELETE: financeiro não apaga mais item em {status} (0 linhas, item mantido)",
               st == "DELETE 0" and await exists_item(item_id), f"{st}; item existe: {await exists_item(item_id)}")

    # ---------- (r) leitura pelo master sem módulo ----------
    await check(c, "R1 o master de teste não tem nenhum módulo",
                "select count(*) from public.profile_modules where profile_id = $1", 0, master)
    n_rep = await c.fetchval("select count(*) from public.reimbursement_reports where profile_id = $1", owner_u)
    got = await status_of(c, lambda: run_as(master, "select count(*) from public.reimbursement_reports "
                                                    "where profile_id = $1", owner_u, fetch=True))
    record("R2 master vê os relatórios de outro usuário", got == n_rep, f"esperado {n_rep}, veio {got}")
    n_it = await c.fetchval("select count(*) from public.reimbursement_items i join public.reimbursement_reports r "
                            "on r.id = i.report_id where r.profile_id = $1", owner_u)
    got = await status_of(c, lambda: run_as(master, "select count(*) from public.reimbursement_items i "
                                                    "join public.reimbursement_reports r on r.id = i.report_id "
                                                    "where r.profile_id = $1", owner_u, fetch=True))
    record("R3 master vê os itens de outro usuário", got == n_it, f"esperado {n_it}, veio {got}")

    # ---------- (g) aprovação ----------
    STATUS = "select status from public.reimbursement_reports where id = $1"
    r_g1 = await report(owner_u, "enviado")
    await expect_ok(c, "G1 master aprova relatório enviado de outro usuário",
                    do(master, APPROVE, r_g1, master, expect="UPDATE 1"))
    await check_row(c, "G2 relatório aprovado com approved_by = o master",
                    "select status, approved_by = $2, approved_at is not null from public.reimbursement_reports "
                    "where id = $1", ("aprovado", True, True), r_g1, master)
    r_g3 = await report(master, "enviado")
    st = await status_of(c, do(master, APPROVE, r_g3, master))
    s = await c.fetchval(STATUS, r_g3)
    record("G3 master não aprova o PRÓPRIO relatório (0 linhas, continua enviado)",
           st == "UPDATE 0" and s == "enviado", f"{st}; status {s}")
    r_g4 = await report(owner_u, "rascunho")
    st = await status_of(c, do(master, APPROVE, r_g4, master))
    s = await c.fetchval(STATUS, r_g4)
    record("G4 master não aprova relatório em rascunho (0 linhas, continua rascunho)",
           st == "UPDATE 0" and s == "rascunho", f"{st}; status {s}")
    r_g5 = await report(owner_u, "enviado")
    st = await status_of(c, do(fin, APPROVE, r_g5, fin))
    s = await c.fetchval(STATUS, r_g5)
    record("G5 financeiro que não é master não aprova (0 linhas, continua enviado)",
           st == "UPDATE 0" and s == "enviado", f"{st}; status {s}")
    r_g6 = await report(owner_u, "enviado")
    await expect_ok(c, "G6 master rejeita relatório enviado sem preencher approved_by (como o rejectReport do app)",
                    do(master, "update public.reimbursement_reports set status = 'rejeitado', "
                               "rejection_reason = 'teste 052' where id = $1", r_g6, expect="UPDATE 1"))
    await check_row(c, "G7 relatório rejeitado com approved_by nulo",
                    "select status, approved_by is null from public.reimbursement_reports where id = $1",
                    ("rejeitado", True), r_g6)
    r_g8 = await report(owner_u, "enviado")
    await expect_fail(c, "G8 gatilho de guarda: master aprovando e mudando period_start é recusado",
                      do(master, "update public.reimbursement_reports set status = 'aprovado', approved_by = $2, "
                                 "approved_at = now(), period_start = period_start - 1 where id = $1", r_g8, master),
                      "42501", "na aprovação só podem mudar")
    r_g9 = await report(owner_u, "enviado")
    await expect_ok(c, "G9 gatilho de guarda: master mudando só status, approved_by e approved_at passa",
                    do(master, APPROVE, r_g9, master, expect="UPDATE 1"))
    r_g10 = await report(owner_u, "enviado")
    await expect_fail(c, "G10 aprovar sem approved_by é recusado pela RLS (WITH CHECK)",
                      do(master, "update public.reimbursement_reports set status = 'aprovado' where id = $1", r_g10),
                      "42501", RLS)

    # ---------- (v) validação do total ----------
    # taxas de teste em 2001 (as reais começam em 2026; sem sobreposição)
    await c.execute("insert into public.reimbursement_rate_rules (type, value, unit, effective_start_date, "
                    "effective_end_date, notes) values "
                    "('deslocamento_escritorio', 1.23, 'por_km', '2001-01-01', '2001-12-31', $1::text), "
                    "('visita_cliente', 2.34, 'por_km', '2001-01-01', '2001-12-31', $1::text), "
                    "('alimentacao', 45.67, 'valor_fixo_diario', '2001-01-01', '2001-12-31', $1::text)", TAG)
    proj = await c.fetchval("insert into public.projects (name, owner_id) values ($1::text, $2) returning id",
                            f"TESTE 052 {TAG}", owner_u)
    D = f"TESTE 052 {TAG}"

    def km(total, rate="1.23", date="2001-06-01", typ="deslocamento_escritorio", project=None, category=cat):
        # km 10, pedágio 5
        return do(owner_u, INS_ITEM, r_rasc, typ, project, category, date, D, "10", rate, "5", "0", total,
                  expect="INSERT 0 1")

    await expect_ok(c, "V1 item de km com total certo passa (10 x 1,23 + 5 = 17,30)", km("17.30"))
    await expect_fail(c, "V2 item de km com total errado recusado", km("20.00"), "23514", "não bate com km_traveled")
    await expect_fail(c, "V3 item de km com km_rate diferente da taxa vigente recusado",
                      km("20.00", rate="1.50"), "23514", "km_rate")
    await expect_fail(c, "V4 item sem taxa vigente na data (1990-01-01) recusado com mensagem clara",
                      km("17.30", date="1990-01-01"), "23514", "sem taxa vigente")

    def meal(total):
        return do(owner_u, INS_ITEM, r_rasc, "alimentacao", None, cat, "2001-06-01", D, None, None, "0", total, total,
                  expect="INSERT 0 1")

    await expect_fail(c, "V5 alimentação com valor diferente da diária recusada", meal("40.00"), "23514",
                      "diária vigente")
    await expect_ok(c, "V6 alimentação com o valor exato da diária passa", meal("45.67"))

    def other(other_amount, total):
        return do(owner_u, INS_ITEM, r_rasc, "outros", None, cat, "2001-06-01", D, None, None, "0", other_amount,
                  total, expect="INSERT 0 1")

    await expect_fail(c, "V7 'outros' com total diferente de other_amount recusado", other("9.00", "10.00"),
                      "23514", 'item "outros"')
    await expect_ok(c, "V8 'outros' com total igual a other_amount passa", other("10.00", "10.00"))
    await expect_ok(c, "V9 visita_comercial usa a taxa de visita_cliente (10 x 2,34 + 5 = 28,40)",
                    km("28.40", rate="2.34", typ="visita_comercial", project=proj, category=None))
    i_km = await c.fetchval(INS_ITEM + " returning id", r_rasc, "deslocamento_escritorio", None, cat, "2001-06-01",
                            D, "10", "1.23", "5", "0", "17.30")
    await c.execute("update public.reimbursement_rate_rules set value = 9.99 "
                    "where notes = $1::text and type = 'deslocamento_escritorio'", TAG)
    await expect_ok(c, "V10 UPDATE só de receipt_path não reconfere o total (taxa mudou depois)",
                    do(owner_u, "update public.reimbursement_items set receipt_path = 'comprovantes/v10.pdf' "
                                "where id = $1", i_km, expect="UPDATE 1"))
    await expect_fail(c, "V11 contraste: UPDATE que toca total_amount é reconferido e recusado com a taxa nova",
                      do(owner_u, "update public.reimbursement_items set total_amount = total_amount where id = $1",
                         i_km), "23514", "km_rate")

    # ---------- (c) comprovante ----------
    await check_row(c, "C1 reimbursement_items.receipt_path: text, aceita nulo, sem padrão",
                    "select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'reimbursement_items' "
                    "and column_name = 'receipt_path'", ("text", "YES", None))
    await check(c, "C2 item gravado sem comprovante fica com receipt_path nulo",
                "select receipt_path is null from public.reimbursement_items where id = $1", True, i_own)

    async def set_receipt():
        st = await run_as(owner_u, "update public.reimbursement_items set receipt_path = 'comprovantes/c3.pdf' "
                                   "where id = $1", i_own)
        assert st == "UPDATE 1", f"esperado 'UPDATE 1', veio {st!r}"
        v = await c.fetchval("select receipt_path from public.reimbursement_items where id = $1", i_own)
        assert v == "comprovantes/c3.pdf", f"receipt_path veio {v!r}"
    await expect_ok(c, "C3 dono grava texto em receipt_path, sem validação", set_receipt)
    r_c4 = await report(owner_u, "rascunho")
    await item_outros(r_c4)
    await expect_ok(c, "C4 relatório com item 'outros' sem comprovante ainda pode ser enviado (sem exigência na 052)",
                    do(owner_u, "update public.reimbursement_reports set status = 'enviado' where id = $1", r_c4,
                       expect="UPDATE 1"))

    # ---------- (d) rateio padrão por time ----------
    x_team = await c.fetchval("insert into public.teams (name) values ($1::text) returning id", f"TESTE 052 {TAG}")
    rule_id = {name: await c.fetchval("select id from public.allocation_rules where name = $1::text", name)
               for name in ("Time Carlos 100%", "Time Weslley 100%", DM_RULE)}
    cases = [("time Carlos", "Carlos", rule_id["Time Carlos 100%"]),
             ("time Weslley", "Weslley", rule_id["Time Weslley 100%"]),
             ("time Diego/Murillo", "Diego/Murillo", rule_id[DM_RULE]),
             ("time sem regra mapeada", None, None),
             ("perfil sem nenhum time (não cai mais no Rateio Sócios 50/50)", "", None)]
    for i, (label, team, expected) in enumerate(cases, start=1):
        uid = await make_user(c, f"rateio{i}")
        if team is None:
            await c.execute("insert into public.team_members (team_id, profile_id) values ($1, $2)", x_team, uid)
        elif team:
            await c.execute("insert into public.team_members (team_id, profile_id) "
                            "select id, $2 from public.teams where name = $1::text", team, uid)
        got = await status_of(c, lambda uid=uid: run_as(uid, f"select {ALLOC_FN.replace('(uuid)', '($1)')}", uid,
                                                        fetch=True))
        record(f"D{i} {label}: regra {'NULL' if expected is None else 'certa'}",
               expected is not None and got == expected or expected is None and got is None,
               f"veio {got!r}")
    await check(c, f"D6 '{DM_RULE}' tem uma única fatia, 100% para o time Diego/Murillo",
                "select count(*) = 1 and bool_and(s.percentage = 100 and t.name = 'Diego/Murillo') "
                "from public.allocation_rule_splits s join public.allocation_rules r on r.id = s.rule_id "
                "join public.teams t on t.id = s.team_id where r.name = $1::text", True, DM_RULE)

    # ---------- (e) regressão ----------
    async def e2e():
        """Fluxo do app com a diária de TESTE cadastrada em (v) (2001, notes = TAG),
        sem depender de taxa real: criar relatório, lançar item de alimentação
        (com a regra de rateio do createItem), enviar, master aprova."""
        rate = await c.fetchval("select value from public.reimbursement_rate_rules "
                                "where notes = $1::text and type = 'alimentacao'", TAG)
        assert rate is not None, "diária de teste de (v) não encontrada"
        rid = await run_as(owner_u, "insert into public.reimbursement_reports (profile_id, period_start, period_end, "
                                    "status) values ($1, '2001-01-01', '2001-12-31', 'rascunho') returning id",
                           owner_u, fetch=True)
        rule = await run_as(owner_u, f"select {ALLOC_FN.replace('(uuid)', '($1)')}", owner_u, fetch=True)
        st = await run_as(owner_u, "insert into public.reimbursement_items (report_id, type, cost_center_id, "
                                   "expense_date, description, other_amount, total_amount, allocation_rule_id) "
                                   "values ($1, 'alimentacao', $2, '2001-06-01', $3::text, $4, $4, $5)",
                          rid, cat, D, rate, rule)
        assert st == "INSERT 0 1", f"lançar item: {st!r}"
        st = await run_as(owner_u, "update public.reimbursement_reports set status = 'enviado' where id = $1", rid)
        assert st == "UPDATE 1", f"enviar: {st!r}"
        st = await run_as(master, APPROVE, rid, master)
        assert st == "UPDATE 1", f"aprovar: {st!r}"
        return rid

    rid = await expect_ok(c, "E1 fluxo de ponta a ponta: rascunho -> item -> enviar -> master aprova", e2e)
    await check_row(c, "E2 relatório do fluxo aprovado pelo master",
                    "select status, approved_by = $2 from public.reimbursement_reports where id = $1",
                    ("aprovado", True), rid, master)
    for t in OUT_OF_SCOPE:
        await check(c, f"E3 {t}: colunas, policies e gatilhos iguais aos de antes", TABLE_STRUCT_SQL,
                    before["struct"][t], t)


async def post_check(dsn, before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 coluna reimbursement_items.receipt_path ausente",
                        "select count(*) from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'reimbursement_items' and column_name = 'receipt_path'", 0)
            await check(c2, "L2 policies de reimbursement_items e reimbursement_reports iguais às de antes",
                        POLICIES_SQL, before["policies"])
            await check(c2, "L3 reimbursement_items com só reimbursement_items_via_report (ALL), como no ROLLBACK",
                        "select string_agg(policyname::text || ':' || cmd::text, ',') from pg_policies "
                        "where schemaname = 'public' and tablename = 'reimbursement_items'",
                        "reimbursement_items_via_report:ALL")
            await check(c2, "L4 approve volta a has_permission(write) e o SELECT dos relatórios sem is_master",
                        "select bool_and(case policyname when 'reimbursement_reports_approve' then "
                        "qual like '%has_permission(''reimbursement_reports''::text, ''write''::text)%' "
                        "and qual not like '%is_master%' else qual not like '%is_master%' end) "
                        "from pg_policies where schemaname = 'public' and tablename = 'reimbursement_reports' "
                        "and policyname in ('reimbursement_reports_approve', 'reimbursement_reports_own')", True)
            await check(c2, "L5 as 2 funções de gatilho da 052 ausentes",
                        "select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
                        "and proname = any($1::text[])", 0, NEW_FUNC_NAMES)
            await check(c2, "L6 gatilhos de reimbursement_items e reimbursement_reports iguais aos de antes",
                        TRIGGERS_SQL, before["triggers"])
            await check(c2, "L7 default_allocation_rule_for_profile igual à de antes (md5)", ALLOC_MD5_SQL,
                        before["alloc_md5"])
            await check(c2, f"L8 regra '{DM_RULE}' ausente",
                        "select count(*) from public.allocation_rules where name = $1::text", 0, DM_RULE)
            record("L9 reimbursement_rate_rules igual ao de antes (contagem + md5)",
                   tuple(await c2.fetchrow(RATES_FP_SQL)) == before["rates_fp"])
            await check(c2, "L10 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            await check(c2, "L11 nenhum time ou projeto de teste",
                        "select (select count(*) from public.teams where name like 'TESTE 052%') + "
                        "(select count(*) from public.projects where name like 'TESTE 052%')", 0)
    finally:
        await c2.close()


async def main():
    dsn = read_dsn()
    sql = MIGRATION.read_text(encoding="utf-8")
    c = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    tr = c.transaction()
    started = False
    try:
        before = await preconditions(c)
        await tr.start()
        started = True
        await run_tests(c, sql, before)
    finally:
        if started:
            await tr.rollback()
            print("\nTransação DESFEITA (rollback).")
        await c.close()

    await post_check(dsn, before)

    failed = [n for n, ok in results if not ok]
    print(f"\nResumo: {len(results) - len(failed)} OK, {len(failed)} falhas, de {len(results)} verificações")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
