"""Teste da migration 051 no STAGING (que já tem da 043 à 050 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_051_staging.py

A 051 é aplicada dentro da transação e, sobre ela, rodam: A (coluna
contracts.billing_entity_id, estrutura e dados existentes), B (função
contract_billing_entity_id), C (gatilho de INSERT: contrato já encerrado),
D (gatilho da SPE do contrato), E (regressão: close_deal de ponta a ponta
antes e depois, close_contract da 049 e os gatilhos juntos) e F (permissões).

Regras:
- Só roda com DATABASE_URL de backend/.env.staging com us-west-2 e a ref de
  staging, sem a ref de produção (checado antes de qualquer conexão).
- Aborta se server_version_num < 150000, se a 049 ou a 050 não estiverem
  aplicadas (close_contract ou taxpayer_profiles ausente) ou se a 051 já
  estiver (contracts.billing_entity_id ou contract_billing_entity_id existe).
- Aplica a 051 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint desfeito são
  desfeitos junto com ele. O caso do limite (D11) roda num savepoint próprio,
  também desfeito.
- contracts é comparado sem billing_entity_id (a única coluna que a 051 cria).
- Usuários fictícios @example.invalid; nada de e-mail, senha, chave ou DSN
  impresso. Nenhum commit.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 66 verificações
  CD0 1 (close_deal antes) + M0 1                                       -> 2
  + (a) A1 a A9                                                         -> 9
  + (b) B1 a B9                                                         -> 9
  + (c) C1 a C7 7, C8 x 2 papéis 2, C9 1                                -> 10
  + (d) D1, D2, D3, D4, D5, D5b, D6, D7, D8, D10, D11 11,
        D12 1, D13 x 2 papéis 2, D14 1                                  -> 15
  + (e) CD1, CD2, CD3 3 (close_deal depois) + E1 a E4 4                 -> 7
  + (f) F1 a F4                                                         -> 4
  + pós-rollback L1 a L10                                               -> 10
  2 + 9 + 9 + 10 + 15 + 7 + 4 + 10 = 66
Se a M0 falhar, o script para logo depois: CD0 + M0 + L1 a L10 = 12 verificações.
"""
import asyncio
import itertools
import json
import secrets
import sys
from pathlib import Path

import asyncpg

import _lib

REPO = Path(r"C:\Users\pmon_admin\Documents\gestao-obras")
ENV_FILE = REPO / "backend" / ".env.staging"
MIGRATION = REPO / "backend" / "migrations" / "051_contract_billing_entity.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste051-" + secrets.token_hex(4)
BE_FN = "public.contract_billing_entity_id(uuid)"
INSERT_GUARD_FN = "public.fn_contracts_guard_insert()"
BE_GUARD_FN = "public.fn_contracts_guard_billing_entity()"
NEW_FUNC_NAMES = ["contract_billing_entity_id", "fn_contracts_guard_insert", "fn_contracts_guard_billing_entity"]
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
# contracts sem a coluna que a 051 cria
CONTRACTS_STRUCT_SQL = ("select md5(coalesce(string_agg(column_name::text || ':' || data_type::text || ':' || "
                        "is_nullable::text || ':' || coalesce(column_default::text, ''), ',' order by ordinal_position), "
                        "'')) from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contracts' and column_name <> 'billing_entity_id'")
CONTRACTS_FP_SQL = ("select count(*), md5(coalesce(string_agg((to_jsonb(x) - 'billing_entity_id')::text, ',' "
                    "order by x.id), '')) from public.contracts x")
DLD_COMMENT_SQL = ("select col_description('public.contracts'::regclass, a.attnum) from pg_attribute a "
                   "where a.attrelid = 'public.contracts'::regclass and a.attname = 'document_lead_days'")
CONTRACT_TRIGGERS_SQL = ("select string_agg(tgname::text, ',' order by tgname) from pg_trigger "
                         "where tgrelid = 'public.contracts'::regclass and not tgisinternal")

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


async def as_anon(c):
    await c.execute("set local role anon")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', $1::text, true)", json.dumps({"role": "anon"}))


async def as_service_role(c):
    await c.execute("set local role service_role")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', $1::text, true)", json.dumps({"role": "service_role"}))


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
    """Como na 049, mais `contains`: um trecho que a mensagem do erro precisa ter
    (para saber que foi o gatilho certo, e não a RLS, que também dá 42501)."""
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


async def new_client_code(c):
    code = None
    while not code or await c.fetchval("select exists (select 1 from public.clients where code = $1::text)", code):
        code = "Q" + secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return code


def cnpj():
    return "".join(secrets.choice("0123456789") for _ in range(14))


async def close_deal_flow(c, uid, *, check_be=False):
    """Fluxo de ponta a ponta do close_deal (mesmo da 049): cliente, projeto,
    proposta e fechamento como authenticated com módulo crm. Tudo num savepoint
    SEMPRE desfeito. Devolve só fatos comparáveis (sem ids)."""
    sp = c.transaction()
    await sp.start()
    try:
        client_id = await c.fetchval(
            "insert into public.clients (code, legal_name) values ($1::text, 'TESTE 051 CD') returning id",
            await new_client_code(c))
        project_id = await c.fetchval(
            "insert into public.projects (name, owner_id, client_id) values ($1::text, $2, $3) returning id",
            f"TESTE 051 CD {TAG}", uid, client_id)
        service_type_id = await c.fetchval("select id from public.service_types order by code limit 1")
        await c.execute("insert into public.proposals (project_id, value, payment_type, service_type_id) "
                        "values ($1, 1000, 'parcela_unica', $2)", project_id, service_type_id)
        await as_user(c, uid)
        contract_id = await c.fetchval(
            "select public.close_deal($1, 'TESTE 051 LTDA', $2::text, 'end', 'rep', '000', 'role', "
            "'SPE TESTE 051 CD', $3::text, 'end spe', null)", project_id, cnpj(), cnpj())
        await as_owner(c)
        res = {
            "contrato_criado": await c.fetchval("select exists (select 1 from public.contracts where id = $1)",
                                                contract_id),
            "contrato_status": await c.fetchval("select status from public.contracts where id = $1", contract_id),
            "proposta_status": await c.fetchval("select status from public.proposals where project_id = $1",
                                                project_id),
            "projeto_estagio": await c.fetchval("select pipeline_stage from public.projects where id = $1",
                                                project_id),
            "spe_criada": await c.fetchval("select exists (select 1 from public.billing_entities "
                                           "where project_id = $1)", project_id),
        }
        if check_be:
            res["billing_entity_id_nulo"] = await c.fetchval(
                "select billing_entity_id is null from public.contracts where id = $1", contract_id)
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
    if not await c.fetchval("select to_regprocedure('public.close_contract(uuid, date, text)') is not null"):
        abort("a 049 não está aplicada (close_contract ausente)")
    if not await c.fetchval("select to_regclass('public.taxpayer_profiles') is not null"):
        abort("a 050 não está aplicada (taxpayer_profiles ausente)")
    if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contracts' and column_name = 'billing_entity_id')"):
        abort("a 051 parece já aplicada (contracts.billing_entity_id existe)")
    if await c.fetchval("select to_regprocedure($1::text) is not null", BE_FN):
        abort("a 051 parece já aplicada (contract_billing_entity_id existe)")
    print(f"contratos antes da 051: {await c.fetchval('select count(*) from public.contracts')}")
    return {"close_deal": await c.fetchval(CLOSE_DEAL_MD5_SQL),
            "contracts_struct": await c.fetchval(CONTRACTS_STRUCT_SQL),
            "contracts_fp": tuple(await c.fetchrow(CONTRACTS_FP_SQL)),
            "dld_comment": await c.fetchval(DLD_COMMENT_SQL),
            "triggers": await c.fetchval(CONTRACT_TRIGGERS_SQL)}


async def run_tests(c, sql, before):
    # close_deal de ponta a ponta ANTES da 051 (usuário fictício com crm)
    cd_user = await make_user(c, "cd")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'crm')", cd_user)
    cd_before = await close_deal_flow(c, cd_user)
    record("CD0 close_deal antes da 051 executa sem erro", "FALHOU" not in cd_before, str(cd_before))

    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 051 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 051 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # ---------- (a) coluna, estrutura e dados existentes ----------
    await check_row(c, "A1 contracts.billing_entity_id: uuid, aceita nulo, sem padrão",
                    "select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'contracts' and column_name = 'billing_entity_id'",
                    ("uuid", "YES", None))
    await check(c, "A2 FK para billing_entities(id) sem cascade (on delete e on update no action)",
                "select count(*) from pg_constraint where conrelid = 'public.contracts'::regclass and contype = 'f' "
                "and confrelid = 'public.billing_entities'::regclass and confdeltype = 'a' and confupdtype = 'a' "
                "and conkey = array[(select attnum from pg_attribute where attrelid = 'public.contracts'::regclass "
                "and attname = 'billing_entity_id')]::int2[]", 1)
    await check(c, "A3 índice parcial idx_contracts_billing_entity onde não é nulo",
                "select indexdef like '%(billing_entity_id) WHERE (billing_entity_id IS NOT NULL)%' from pg_indexes "
                "where schemaname = 'public' and indexname = 'idx_contracts_billing_entity'", True)
    await check(c, "A4 comentário da coluna (vazio = a SPE do projeto)",
                "select col_description('public.contracts'::regclass, a.attnum) like '%Vazio = a SPE do projeto%' "
                "from pg_attribute a where a.attrelid = 'public.contracts'::regclass and a.attname = 'billing_entity_id'",
                True)
    await check(c, "A5 demais colunas de contracts iguais (md5 da estrutura sem billing_entity_id)",
                CONTRACTS_STRUCT_SQL, before["contracts_struct"])
    await check(c, "A6 close_deal com o mesmo md5 do corpo antes e depois da 051", CLOSE_DEAL_MD5_SQL,
                before["close_deal"])
    record("A7 contratos existentes iguais fora da coluna nova (contagem + md5)",
           tuple(await c.fetchrow(CONTRACTS_FP_SQL)) == before["contracts_fp"])
    await check(c, "A8 nenhum contrato existente recebeu billing_entity_id",
                "select count(*) from public.contracts where billing_entity_id is not null", 0)
    await check(c, "A9 document_lead_days comentado como sem significado documentado",
                f"select ({DLD_COMMENT_SQL}) like 'Sem significado documentado%'", True)

    # ---------- dados de apoio (dono da migration) ----------
    fin = await make_user(c, "fin")
    crm = await make_user(c, "crm")
    none_ = await make_user(c, "sem")
    full = await make_user(c, "full")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro'), ($2, 'crm'), "
                    "($3, 'financeiro'), ($3, 'crm')", fin, crm, full)
    cli_a = await c.fetchval("insert into public.clients (code, legal_name) values ($1::text, 'TESTE 051 A') "
                             "returning id", await new_client_code(c))
    cli_b = await c.fetchval("insert into public.clients (code, legal_name) values ($1::text, 'TESTE 051 B') "
                             "returning id", await new_client_code(c))

    async def project(label, client):
        return await c.fetchval("insert into public.projects (name, owner_id, client_id) values ($1::text, $2, $3) "
                                "returning id", f"TESTE 051 {label} {TAG}", fin, client)

    async def spe(label, proj):
        return await c.fetchval("insert into public.billing_entities (project_id, legal_name, cnpj) "
                                "values ($1, $2::text, $3::text) returning id", proj, f"SPE TESTE 051 {label}", cnpj())

    p_a1 = await project("A1", cli_a)
    p_a2 = await project("A2", cli_a)
    p_b = await project("B", cli_b)
    p_n = await project("N", None)
    p_nospe = await project("SEM SPE", cli_a)
    be_a1 = await spe("A1", p_a1)
    be_a2 = await spe("A2", p_a2)
    be_b = await spe("B", p_b)
    be_n = await spe("N", p_n)
    svc = await c.fetchval("select id from public.service_types order by code limit 1")
    codes = itertools.count(1)

    async def contract(proj, be=None):
        """Contrato criado pelo dono (sem usuário logado), ativo."""
        return await c.fetchval(
            "insert into public.contracts (project_id, contract_code, contract_label, service_type_id, payment_type, "
            "fee_value, start_date, billing_entity_id) values ($1, $2::text, 'TESTE 051', $3, 'mensal_recorrente', "
            "1000, '2026-01-01', $4) returning id", proj, f"{next(codes):02d}", svc, be)

    async def run_as(uid, q, *args, fetch=False):
        # sem try/finally: num savepoint que falha, o rollback dele já desfaz o papel
        if uid is None:
            await as_anon(c)
        else:
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

    # ---------- (b) contract_billing_entity_id ----------
    FN = "select public.contract_billing_entity_id($1::uuid)"
    kb_null = await contract(p_a1)
    kb_set = await contract(p_a1, be_a2)
    kb_nospe = await contract(p_nospe)
    got = await run_as(crm, FN, kb_null, fetch=True)
    record("B1 campo nulo: devolve a SPE do projeto", got == be_a1, f"é a SPE do projeto: {got == be_a1}")
    got = await run_as(crm, FN, kb_set, fetch=True)
    record("B2 campo preenchido: devolve a SPE do contrato", got == be_a2, f"é a SPE do contrato: {got == be_a2}")
    await check(c, "B3 contrato inexistente: nulo", FN, None,
                await c.fetchval("select gen_random_uuid()"))
    got = await run_as(crm, FN, kb_nospe, fetch=True)
    record("B4 projeto sem SPE: nulo", got is None, f"veio nulo: {got is None}")
    got = await run_as(none_, FN, kb_null, fetch=True)
    record("B5 usuário sem leitura de contratos recebe nulo (security invoker, RLS de quem chama)", got is None,
           f"veio nulo: {got is None}")
    await check(c, "B6 anon sem EXECUTE em contract_billing_entity_id",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, BE_FN)
    await check(c, "B7 authenticated com EXECUTE em contract_billing_entity_id",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, BE_FN)
    await check(c, "B8 security invoker e search_path vazio",
                "select not prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, BE_FN)
    await check(c, "B9 language sql e stable",
                "select l.lanname = 'sql' and p.provolatile = 's' from pg_proc p join pg_language l "
                "on l.oid = p.prolang where p.oid = to_regprocedure($1::text)", True, BE_FN)

    # ---------- (c) gatilho de INSERT: contrato já encerrado ----------
    INS = ("insert into public.contracts (project_id, contract_code, contract_label, service_type_id, payment_type, "
           "fee_value, start_date, status, termination_notice_date, termination_reason) values ($1, $2::text, "
           "'TESTE 051', $3, 'mensal_recorrente', 1000, '2026-01-01', $4::text, ($5::text)::date, $6::text)")

    def ins_args(status="ativo", notice=None, reason=None):
        return (p_a1, f"{next(codes):02d}", svc, status, notice, reason)

    await expect_fail(c, "C1 pela API, status 'encerrado' recusado",
                      do(crm, INS, *ins_args(status="encerrado")), "42501", "criado já encerrado")
    await expect_fail(c, "C2 pela API, termination_notice_date preenchida recusada",
                      do(crm, INS, *ins_args(notice="2026-05-01")), "42501", "dados de encerramento")
    await expect_fail(c, "C3 pela API, termination_reason preenchido recusado",
                      do(crm, INS, *ins_args(reason="motivo")), "42501", "dados de encerramento")
    await expect_fail(c, "C4 pela API, termination_reason vazio também recusado",
                      do(crm, INS, *ins_args(reason="")), "42501", "dados de encerramento")
    await expect_ok(c, "C5 pela API, contrato 'ativo' normal aceito",
                    do(crm, INS, *ins_args(), expect="INSERT 0 1"))
    await expect_ok(c, "C6 sem usuário logado (dono/migration), encerrado com dados de encerramento passa",
                    own(INS, *ins_args(status="encerrado", notice="2026-05-01", reason="migração"),
                        expect="INSERT 0 1"))

    async def as_service_insert():
        await as_service_role(c)
        st = await c.execute(INS, *ins_args(status="encerrado", notice="2026-05-01", reason="carga"))
        await as_owner(c)
        assert st == "INSERT 0 1", f"esperado 'INSERT 0 1', veio {st!r}"
    await expect_ok(c, "C7 service_role (sem usuário logado), encerrado com dados de encerramento passa",
                    as_service_insert)
    for role in ("anon", "authenticated"):
        await check(c, f"C8 {role} sem EXECUTE na função do gatilho de INSERT",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, INSERT_GUARD_FN)
    # tgtype 7 = ROW (1) + BEFORE (2) + INSERT (4); tgenabled 'O' = ligado
    await check(c, "C9 trg_contracts_guard_insert: BEFORE INSERT, por linha, ligado",
                "select count(*) from pg_trigger where tgname = 'trg_contracts_guard_insert' "
                "and tgrelid = 'public.contracts'::regclass and tgtype = 7 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text)", 1, INSERT_GUARD_FN)

    # ---------- (d) gatilho da SPE do contrato ----------
    UPD_BE = "update public.contracts set billing_entity_id = $2 where id = $1"
    k1 = await contract(p_a1)
    k_n = await contract(p_n)
    k_m = await contract(p_a1, be_a2)
    WRONG = "não pode ser a tomadora"
    await expect_ok(c, "D1 campo nulo passa", do(crm, UPD_BE, k1, None, expect="UPDATE 1"))
    await expect_ok(c, "D2 SPE do mesmo projeto passa", do(crm, UPD_BE, k1, be_a1, expect="UPDATE 1"))
    await expect_ok(c, "D3 SPE de outro projeto do mesmo cliente passa", do(crm, UPD_BE, k1, be_a2, expect="UPDATE 1"))
    await expect_fail(c, "D4 SPE de projeto de outro cliente recusada", do(crm, UPD_BE, k1, be_b), "23514", WRONG)
    await expect_fail(c, "D5 contrato de projeto sem cliente, SPE de outro projeto recusada",
                      do(crm, UPD_BE, k_n, be_a1), "23514", WRONG)
    await expect_fail(c, "D5b SPE de projeto sem cliente recusada", do(crm, UPD_BE, k1, be_n), "23514", WRONG)
    await expect_fail(c, "D6 SPE inexistente cai na FK", do(crm, UPD_BE, k1, await c.fetchval("select gen_random_uuid()")),
                      "23503")
    INS_BE = ("insert into public.contracts (project_id, contract_code, contract_label, service_type_id, payment_type, "
              "fee_value, start_date, billing_entity_id) values ($1, $2::text, 'TESTE 051', $3, 'mensal_recorrente', "
              "1000, '2026-01-01', $4)")
    await expect_fail(c, "D7 INSERT com SPE de outro cliente recusado",
                      do(crm, INS_BE, p_a1, f"{next(codes):02d}", svc, be_b), "23514", WRONG)
    await expect_fail(c, "D8 UPDATE do project_id é reavaliado (SPE do cliente A, projeto do cliente B)",
                      do(crm, "update public.contracts set project_id = $2 where id = $1", k_m, p_b), "23514", WRONG)
    await expect_fail(c, "D10 sem usuário logado (dono/migration) também é barrado", own(UPD_BE, k1, be_b),
                      "23514", WRONG)

    # D11: o limite documentado; savepoint próprio, desfeito
    sp = c.transaction()
    await sp.start()
    k_l = await contract(p_a1, be_a2)
    st = await status_of(c, own("update public.projects set client_id = $2 where id = $1", p_a2, cli_b))
    still = await c.fetchval("select billing_entity_id = $2 from public.contracts where id = $1", k_l, be_a2)
    await sp.rollback()
    record("D11 LIMITE: mudar o client_id do projeto da SPE depois não reavalia os contratos",
           st == "UPDATE 1" and still is True, f"{st}; contrato continua com a SPE: {still}")

    await check(c, "D12 função da SPE: security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, BE_GUARD_FN)
    for role in ("anon", "authenticated"):
        await check(c, f"D13 {role} sem EXECUTE na função do gatilho da SPE",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, BE_GUARD_FN)
    # tgtype 23 = ROW (1) + BEFORE (2) + INSERT (4) + UPDATE (16)
    await check(c, "D14 trg_contracts_guard_billing_entity: BEFORE INSERT OR UPDATE OF billing_entity_id, project_id",
                "select count(*) from pg_trigger where tgname = 'trg_contracts_guard_billing_entity' "
                "and tgrelid = 'public.contracts'::regclass and tgtype = 23 and tgenabled = 'O' "
                "and tgfoid = to_regprocedure($1::text) "
                "and pg_get_triggerdef(oid) like '%UPDATE OF billing_entity_id, project_id ON public.contracts%'",
                1, BE_GUARD_FN)

    # ---------- (e) regressão ----------
    cd_after = await close_deal_flow(c, cd_user, check_be=True)
    record("CD1 close_deal depois da 051 executa sem erro", "FALHOU" not in cd_after, str(cd_after))
    after_cmp = {k: v for k, v in cd_after.items() if k != "billing_entity_id_nulo"}
    record("CD2 resultado do fechamento igual antes e depois da 051", after_cmp == cd_before,
           f"antes {cd_before}, depois {after_cmp}")
    record("CD3 contrato criado pelo close_deal fica com billing_entity_id nulo",
           cd_after.get("billing_entity_id_nulo") is True, str(cd_after))

    k_z = await contract(p_a1)
    k_z2 = await contract(p_a1)
    await expect_ok(c, "E1 close_contract (049) encerra pela função com crm + financeiro",
                    lambda: run_as(full, "select * from public.close_contract($1::uuid, current_date, 'teste 051')",
                                   k_z, fetch=True))
    await check_row(c, "E2 contrato encerrado, end_date = aviso + 30",
                    "select status, end_date = current_date + 30 from public.contracts where id = $1",
                    ("encerrado", True), k_z)
    await expect_fail(c, "E3 encerrar direto pela API continua recusado (gatilho da 049)",
                      do(crm, "update public.contracts set status = 'encerrado' where id = $1", k_z2),
                      "42501", "close_contract")
    await check(c, "E4 os 3 gatilhos de guarda (049 e 051) existem juntos e ligados em contracts",
                "select count(*) from pg_trigger where tgrelid = 'public.contracts'::regclass and tgenabled = 'O' "
                "and tgname in ('trg_contracts_guard_close', 'trg_contracts_guard_insert', "
                "'trg_contracts_guard_billing_entity')", 3)

    # ---------- (f) permissões ----------
    k_f = await contract(p_a1)
    await expect_ok(c, "F1 crm grava billing_entity_id", do(crm, UPD_BE, k_f, be_a2, expect="UPDATE 1"))
    st = await status_of(c, do(fin, UPD_BE, k_f, be_a1))
    still = await c.fetchval("select billing_entity_id = $2 from public.contracts where id = $1", k_f, be_a2)
    record("F2 financeiro não grava (contracts só aceita gravação do crm): 0 linhas e valor mantido",
           st == "UPDATE 0" and still is True, f"{st}; valor mantido: {still}")
    n = await status_of(c, lambda: run_as(none_, "select count(*) from public.contracts", fetch=True))
    record("F3 usuário sem módulo não vê nenhum contrato", n == 0, f"veio {n}")
    n = await status_of(c, lambda: run_as(None, "select count(*) from public.contracts", fetch=True))
    record("F4 anon não lê contratos (sem privilégio ou 0 linhas)",
           n == 0 or (isinstance(n, str) and n.startswith("ERRO 42501")), f"veio {n}")


async def post_check(dsn, before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 coluna contracts.billing_entity_id ausente",
                        "select count(*) from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contracts' and column_name = 'billing_entity_id'", 0)
            await check(c2, "L2 as 3 funções da 051 ausentes",
                        "select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
                        "and proname = any($1::text[])", 0, NEW_FUNC_NAMES)
            await check(c2, "L3 gatilhos de contracts iguais aos de antes", CONTRACT_TRIGGERS_SQL, before["triggers"])
            await check(c2, "L4 índice idx_contracts_billing_entity ausente",
                        "select to_regclass('public.idx_contracts_billing_entity') is null", True)
            await check(c2, "L5 comentário de document_lead_days igual ao de antes", DLD_COMMENT_SQL,
                        before["dld_comment"])
            await check(c2, "L6 close_deal igual ao de antes do teste", CLOSE_DEAL_MD5_SQL, before["close_deal"])
            await check(c2, "L7 estrutura de contracts igual à de antes", CONTRACTS_STRUCT_SQL, before["contracts_struct"])
            record("L8 contracts igual ao de antes (contagem + md5)",
                   tuple(await c2.fetchrow(CONTRACTS_FP_SQL)) == before["contracts_fp"])
            await check(c2, "L9 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            await check(c2, "L10 nenhum cliente, projeto ou SPE de teste",
                        "select (select count(*) from public.clients where legal_name like 'TESTE 051%') + "
                        "(select count(*) from public.projects where name like 'TESTE 051%') + "
                        "(select count(*) from public.billing_entities where legal_name like 'SPE TESTE 051%')", 0)
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
