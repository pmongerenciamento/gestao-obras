"""Teste da migration 049 em PRODUÇÃO (que já tem da 045 à 048 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_049_prod.py

A 049 é aplicada dentro da transação e, sobre ela, rodam: a regressão da
046 à 048 (bateria da 046 com o helper de versão, SP1 a SP10, estrutura W,
vigência V, R/N/P/S da 048); e os casos novos da 049: T (colunas e
preenchimento), Q (geração com prazo), I e IE (intervalo de cobrança na
geração e na extensão), XT (extensão com prazo), X (encerramento pela
close_contract com data do aviso), AV (aviso prévio de 30 dias), Z (trigger:
encerrar direto pela API é recusado, pela função é aceito; reabrir pela API é
recusado) e K (estrutura da close_contract).
O master de teste é criado dentro da transação (system_role trocado como
dono, sem usuário logado, o que o trigger da 043 permite) e some no rollback.

Regras:
- Só roda com DATABASE_URL de backend/.env com sa-east-1 e a ref de
  produção, sem a ref de staging (checado antes de qualquer conexão).
- O e-mail do master vem de MASTER_EMAIL em backend/.env (lido junto com o
  DSN, antes de qualquer conexão; aborta se faltar). Não fica no código e
  não é impresso.
- Aborta se server_version_num < 150000, se a 047 ou a 048 não estiverem
  aplicadas, se a 049 já estiver (contracts.term_months ou
  billing_interval_months existe), se o número de masters for diferente
  de 1 ou se esse master não for a conta do Diego (resolvida pelo
  MASTER_EMAIL).
- O master de teste existe só dentro da transação: nada rebaixa nem apaga o
  master real. No fim da transação, os masters entre os perfis reais (ids
  medidos no começo) têm de continuar sendo só o Diego; na conexão nova,
  exatamente 1 master, o Diego.
- Dados reais: ANTES de qualquer teste (logo depois de abrir a transação)
  mede contagem + md5 de auth.users, profiles, teams, profile_modules,
  team_members, contracts, contract_installments, contract_revenue_splits,
  bank_transactions e service_types (guardando os ids), o md5 do perfil +
  módulos do Diego e a contagem de billing_entities, proposals, projects e
  project_stage_history. contracts entra sem as colunas que a 049 cria
  dentro da transação (term_months, billing_interval_months,
  termination_notice_date e termination_reason); proposals, que também
  ganha colunas, só entra pela contagem. No fim da transação compara as linhas
  reais pelos ids e confere que as linhas a mais são só de teste; na
  conexão nova compara tudo inteiro. Nenhuma contagem real escrita no código.
  ATENÇÃO: o md5 de auth.users usa a linha inteira; um login real durante o
  teste (last_sign_in_at) faz DR1/L10 de auth_users falharem sem defeito na 049.
- Aplica a 049 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint que falha são
  desfeitos junto com ele.
- Usuários fictícios @example.invalid; nada de e-mail, senha, chave ou DSN
  impresso. Nenhum commit.
- O horizonte da extensão é calculado a partir do current_date do banco.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 378 verificações
  336 do teste de staging (abaixo)
  + 26 de dados reais no fim da transação:
    DR1 linhas reais intactas pelos ids (10 tabelas) + DR2 Diego
    + DR3 linhas a mais só de teste (10 tabelas) + DR4 masters reais só o Diego
    + DR5 nenhuma linha do fluxo do close_deal com a TAG (4 tabelas)
  + 16 de dados reais na conexão nova:
    L10 tabela inteira igual ao começo (10 tabelas) + L11 Diego + L12 master
    + L13 contagem igual ao começo (4 tabelas)
Detalhe dos 336:
  CD0 1 (close_deal antes) + M0 1 + H1 1 + CD1 a CD7 7 (close_deal depois)
  + (t) T1 a T3 x 2 tabelas = 6, T4, T5, T6, T6b, T7 e T8 x 2 tabelas = 4,
        T9, T10, T10b, T11 = 18
  + bateria da 046 com o helper de versão: (a) 10 + (b) 32 + (c) 21
    + (d) 16 + (e) 10 + (f) 6
  + (g) 30 [G1 crm e sem módulo x 5 funções = 10; G2 1; G3 1;
            G4/G5/G6 x 5 funções = 15; G7 x 2 papéis = 2; G8 1]
  + (s) SP1 a SP10 com p_valid_from = 14
  + (w) estrutura da 047 = 11 [W1 a W8, W9 x 2 papéis, W10]
  + (v) vigência das versões = 31 (os 27 da 047, com V3c, V4b, V4c e V4e
        desdobrados em financeiro não master e master)
  + (r) R0 setup + R1 a R4 = 5
  + (n) N1 a N5 + N6a a N6c = 8
  + (p) P1 a P3 = 3
  + (s2) S1, S2, S3a a S3c, S4, S5 = 7
  + (q) Q1 a Q6b = 14
  + (i) I1 a I7b = 15 [I1/I1b/I1c, I2/I2b/I2c, I3, I4, I4b, I5/I5b, I6/I6b, I7/I7b]
  + (ie) IE1, IE2, IE2b, IE2c, IE2d, IE3, IE3b, IE4, IE4b = 9
  + (xt) XT1 a XT3b = 9
  + (x) X0 a X10c = 19 [X0, X1, X2, X3, X3b a X3e, X4 a X7, X8, X8b, X8c, X9,
        X10, X10b, X10c]
  + (av) AV1, AV2, AV2b, AV2c, AV3, AV3b, AV4, AV4b = 8
  + (z) Z1, Z1b, Z2, Z3, Z4, Z5 x 2 papéis, Z6, Z7, Z7b, Z8, Z9, Z9b, Z10 = 14
  + (k) K1 a K7 = 7
  + pós-rollback L1 a L9 = 9
Se a M0 falhar: CD0 + M0 + 26 + 9 + 16 = 53 verificações.
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
ENV_FILE = REPO / "backend" / ".env"
MASTER_EMAIL = None  # preenchido por read_dsn() com MASTER_EMAIL de backend/.env
REAL_TABLES = [("auth_users", "auth.users", "to_jsonb(x)"),
               ("profiles", "public.profiles", "to_jsonb(x)"),
               ("teams", "public.teams", "to_jsonb(x)"),
               ("profile_modules", "public.profile_modules", "to_jsonb(x)"),
               ("team_members", "public.team_members", "to_jsonb(x)"),
               ("contracts", "public.contracts",
                "(to_jsonb(x) - 'term_months' - 'billing_interval_months' - 'termination_notice_date' "
                "- 'termination_reason')"),
               ("contract_installments", "public.contract_installments", "to_jsonb(x)"),
               ("contract_revenue_splits", "public.contract_revenue_splits", "to_jsonb(x)"),
               ("bank_transactions", "public.bank_transactions", "to_jsonb(x)"),
               ("service_types", "public.service_types", "to_jsonb(x)")]
EXTRA_TABLES = ["billing_entities", "proposals", "projects", "project_stage_history"]
MIGRATION = REPO / "backend" / "migrations" / "049_contract_term_months.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste049-" + secrets.token_hex(4)
CLOSE_FN = "public.close_contract(uuid, date, text)"
OLD_CLOSE_FN = "public.close_contract(uuid, date)"
GUARD_FN = "public.fn_contracts_guard_close()"
# contracts e proposals sem as colunas novas da 049, para comparar antes e depois
CONTRACTS_FP_SQL = ("select count(*), md5(coalesce(string_agg((to_jsonb(x) - 'term_months' - 'billing_interval_months' "
                    "- 'termination_notice_date' - 'termination_reason')::text, ',' "
                    "order by x.id), '')) from public.contracts x")
PROPOSALS_FP_SQL = ("select count(*), md5(coalesce(string_agg((to_jsonb(x) - 'term_months' - 'billing_interval_months')"
                    "::text, ',' order by x.id), '')) from public.proposals x")
IC_COMMENTS_SQL = ("select string_agg(coalesce(col_description(a.attrelid, a.attnum), '<nulo>'), '|' "
                   "order by a.attrelid::regclass::text) from pg_attribute a "
                   "where a.attrelid in ('public.contracts'::regclass, 'public.proposals'::regclass) "
                   "and a.attname = 'installments_count'")
IS_MASTER_FN = "public.is_master()"
SPLITS_DEF_SQL = "select pg_get_functiondef(to_regprocedure('public.set_contract_splits(uuid, date, jsonb, boolean)'))"
SPLITS_SRC_SQL = "select prosrc from pg_proc where oid = to_regprocedure('public.set_contract_splits(uuid, date, jsonb, boolean)')"
IS_MASTER_MD5_SQL = "select md5(pg_get_functiondef(to_regprocedure('public.is_master()')))"
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
            "insert into public.clients (code, legal_name) values ($1::text, 'TESTE 049 CD') returning id", code)
        project_id = await c.fetchval(
            "insert into public.projects (name, owner_id, client_id) values ($1::text, $2, $3) returning id",
            f"TESTE 049 CD {TAG}", uid, client_id)
        service_type_id = await c.fetchval("select id from public.service_types order by code limit 1")
        await c.execute("insert into public.proposals (project_id, value, payment_type, service_type_id, "
                        "scope_description) values ($1, 1000, 'parcela_unica', $2, $3::text)",
                        project_id, service_type_id, f"TESTE 049 CD {TAG}")
        await as_user(c, uid)
        contract_id = await c.fetchval(
            "select public.close_deal($1, 'TESTE 049 LTDA', $2::text, 'end', 'rep', '000', 'role', "
            "$4::text, $3::text, 'end spe', null)",
            project_id, "".join(secrets.choice("0123456789") for _ in range(14)),
            "".join(secrets.choice("0123456789") for _ in range(14)), f"SPE TESTE 049 CD {TAG}")
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
                            "and table_name = 'contract_revenue_splits' and column_name = 'valid_from') "
                            "and to_regprocedure($1::text) is not null and to_regprocedure($2::text) is null",
                            NEW_SPLITS, OLD_SPLITS):
        abort("a 047 não está aplicada")
    if not await c.fetchval(SPLITS_SRC_SQL.replace("select prosrc", "select prosrc like '%exclusivo do master%'")):
        abort("a 048 não está aplicada (set_contract_splits sem a regra do master)")
    if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                        "and table_name = 'contracts' and column_name = 'term_months')"):
        abort("a 049 parece já aplicada (contracts.term_months existe)")
    if await c.fetchval("select exists (select 1 from information_schema.columns where table_schema = 'public' "
                        "and table_name in ('contracts', 'proposals') and column_name = 'billing_interval_months')"):
        abort("a 049 parece já aplicada (billing_interval_months existe)")
    if not await c.fetchval("select to_regprocedure($1::text) is not null", IS_MASTER_FN):
        abort("public.is_master() não existe (043)")

    rows = await c.fetch("select id from auth.users where lower(email) = lower($1::text)", MASTER_EMAIL)
    if len(rows) != 1:
        abort(f"esperada 1 conta com o e-mail do Diego, achou {len(rows)}")
    diego = rows[0]["id"]
    masters = await master_ids(c)
    print(f"masters em profiles: {len(masters)}")
    if len(masters) != 1:
        abort(f"esperado exatamente 1 master, achou {len(masters)}")
    if masters[0] != diego:
        abort("o master existente não é a conta do Diego (resolvida pelo e-mail)")
    print("master existente = conta do Diego (resolvida pelo e-mail)")
    print(f"contratos antes da 049: {await c.fetchval('select count(*) from public.contracts')}; "
          f"propostas: {await c.fetchval('select count(*) from public.proposals')}")
    return {"close_deal": await c.fetchval(CLOSE_DEAL_MD5_SQL),
            "genext": await c.fetchval(GEN_EXT_MD5_SQL),
            "splits_def_md5": await c.fetchval(f"select md5(({SPLITS_DEF_SQL}))"),
            "splits_src": await c.fetchval(SPLITS_SRC_SQL),
            "is_master": await c.fetchval(IS_MASTER_MD5_SQL),
            "ic_comments": await c.fetchval(IC_COMMENTS_SQL),
            "contracts_fp": tuple(await c.fetchrow(CONTRACTS_FP_SQL)),
            "proposals_fp": tuple(await c.fetchrow(PROPOSALS_FP_SQL)),
            "parcelados": await c.fetchval("select count(*) from public.contracts where payment_type = 'parcelado' "
                                           "and installments_count is not null") +
                          await c.fetchval("select count(*) from public.proposals where payment_type = 'parcelado' "
                                           "and installments_count is not null"),
            "diego": diego}


# ---------- dados reais: contagem + md5 ----------
async def master_ids(c, among=None):
    if among is None:
        return [r["id"] for r in await c.fetch("select id from public.profiles where system_role = 'master'")]
    return [r["id"] for r in await c.fetch(
        "select id from public.profiles where system_role = 'master' and id = any($1::uuid[])", among)]


async def table_fp(c, table, expr, ids=None):
    """(contagem, md5) da tabela pela expressão json da linha; com ids, só dessas linhas."""
    where = "where x.id = any($1::uuid[])" if ids is not None else ""
    row = await c.fetchrow(
        f"select count(*) as n, md5(coalesce(string_agg({expr}::text, ',' order by x.id), '')) as h "
        f"from {table} x {where}", *([ids] if ids is not None else []))
    return row["n"], row["h"]


async def diego_fp(c, diego):
    return await c.fetchval(
        "select md5(coalesce((select row_to_json(p)::text from public.profiles p where p.id = $1), '') || '|' || "
        "coalesce((select string_agg(module, ',' order by module) from public.profile_modules "
        "where profile_id = $1), ''))", diego)


def fmt(fp):
    return f"{fp[0]} (md5 {fp[1][:12]}…)"


async def measure_before(c, diego):
    ids, fp = {}, {}
    for key, table, expr in REAL_TABLES:
        ids[key] = [r["id"] for r in await c.fetch(f"select id from {table}")]
        fp[key] = await table_fp(c, table, expr)
    fp["diego"] = await diego_fp(c, diego)
    fp["extra_counts"] = {t: await c.fetchval(f"select count(*) from public.{t}") for t in EXTRA_TABLES}
    print("dados reais antes: " + ", ".join(f"{k}={fmt(fp[k])}" for k, _, _ in REAL_TABLES)
          + f"; Diego md5 {fp['diego'][:12]}…; contagens: {fp['extra_counts']}")
    return ids, fp


async def real_data_in_txn(c, ids, fp_before, diego):
    """Ainda dentro da transação: linhas reais pelos ids guardados; as linhas
    a mais só podem ser de teste (ligadas à TAG desta execução)."""
    print("\n== dados reais (fim da transação) ==")
    for key, table, expr in REAL_TABLES:
        now = await table_fp(c, table, expr, ids[key])
        b = fp_before[key]
        record(f"DR1 {key}: linhas reais intactas (contagem + md5 pelos ids)", now == b,
               f"antes {fmt(b)}, agora {fmt(now)}")
    record("DR2 perfil e módulos do Diego intactos (md5)", await diego_fp(c, diego) == fp_before["diego"])

    test_users = f"(select id from auth.users where email like '{TAG}-%@example.invalid')"
    test_projects = f"(select id from public.projects where name like '%{TAG}')"
    test_contracts = f"(select id from public.contracts where project_id in {test_projects})"
    non_test_extras = {
        "auth_users": f"select count(*) from auth.users where id <> all($1::uuid[]) "
                      f"and email not like '{TAG}-%@example.invalid'",
        "profiles": f"select count(*) from public.profiles where id <> all($1::uuid[]) and id not in {test_users}",
        "teams": f"select count(*) from public.teams where id <> all($1::uuid[]) and name not like '%{TAG}'",
        "profile_modules": f"select count(*) from public.profile_modules where id <> all($1::uuid[]) "
                           f"and profile_id not in {test_users}",
        "team_members": "select count(*) from public.team_members where id <> all($1::uuid[])",
        "contracts": f"select count(*) from public.contracts where id <> all($1::uuid[]) "
                     f"and project_id not in {test_projects}",
        "contract_installments": f"select count(*) from public.contract_installments where id <> all($1::uuid[]) "
                                 f"and contract_id not in {test_contracts}",
        "contract_revenue_splits": f"select count(*) from public.contract_revenue_splits "
                                   f"where id <> all($1::uuid[]) and contract_id not in {test_contracts}",
        "bank_transactions": f"select count(*) from public.bank_transactions where id <> all($1::uuid[]) "
                             f"and external_id not like '{TAG}-%'",
        "service_types": "select count(*) from public.service_types where id <> all($1::uuid[])",
    }
    for key, _, _ in REAL_TABLES:
        await check(c, f"DR3 {key}: linhas a mais são só de teste", non_test_extras[key], 0, ids[key])
    # o master de teste existe dentro da transação; entre os perfis reais, só o Diego
    m = await master_ids(c, ids["profiles"])
    record("DR4 masters entre os perfis reais = só o Diego (o master de teste é fictício)", m == [diego],
           f"{len(m)} master(s) real(is)")

    cd_projects = f"(select id from public.projects where name = 'TESTE 049 CD {TAG}')"
    cd_tag_rows = {
        "billing_entities": f"select count(*) from public.billing_entities "
                            f"where legal_name = 'SPE TESTE 049 CD {TAG}' or project_id in {cd_projects}",
        "proposals": f"select count(*) from public.proposals "
                     f"where scope_description = 'TESTE 049 CD {TAG}' or project_id in {cd_projects}",
        "projects": f"select count(*) from public.projects where name = 'TESTE 049 CD {TAG}'",
        "project_stage_history": f"select count(*) from public.project_stage_history "
                                 f"where project_id in {cd_projects}",
    }
    for t in EXTRA_TABLES:
        await check(c, f"DR5 {t}: nenhuma linha do fluxo do close_deal com a TAG", cd_tag_rows[t], 0)


async def run_tests(c, sql, before):
    close_deal_before = before["close_deal"]
    # close_deal de ponta a ponta ANTES da 049 (usuário fictício com crm)
    cd_user = await make_user(c, "cd")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'crm')", cd_user)
    cd_before = await close_deal_flow(c, cd_user)
    record("CD0 close_deal antes da 049 executa sem erro", "FALHOU" not in cd_before, str(cd_before))

    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 049 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 049 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # (h) close_deal intacto
    await check(c, "H1 close_deal com o mesmo md5 do corpo antes e depois da 049", CLOSE_DEAL_MD5_SQL,
                close_deal_before)

    # ---------- (t) estrutura e preenchimento da 049 ----------
    for t in ("contracts", "proposals"):
        await check_row(c, f"T1 {t}.term_months: integer, aceita nulo",
                        "select data_type::text, is_nullable::text from information_schema.columns "
                        "where table_schema = 'public' and table_name = $1 and column_name = 'term_months'",
                        ("integer", "YES"), t)
        await check(c, f"T2 {t}: check term_months > 0 existe",
                    "select count(*) from pg_constraint where conname = $1 and contype = 'c'", 1,
                    f"{t}_term_months_positive")
        await check(c, f"T3 {t}.installments_count comentado como substituído por term_months",
                    "select coalesce(col_description(($1::text)::regclass, a.attnum), '') like 'Substituído por term_months%' "
                    "from pg_attribute a where a.attrelid = ($1::text)::regclass and a.attname = 'installments_count'",
                    True, f"public.{t}")
    await check(c, "T4 parcelados com installments_count receberam term_months igual (contracts + proposals)",
                "select (select count(*) from public.contracts where payment_type = 'parcelado' "
                "and installments_count is not null and term_months = installments_count) + "
                "(select count(*) from public.proposals where payment_type = 'parcelado' "
                "and installments_count is not null and term_months = installments_count)", before["parcelados"])
    await check(c, "T5 nenhum outro contrato ou proposta recebeu term_months",
                "select (select count(*) from public.contracts where term_months is not null and not "
                "(payment_type = 'parcelado' and installments_count is not null)) + "
                "(select count(*) from public.proposals where term_months is not null and not "
                "(payment_type = 'parcelado' and installments_count is not null))", 0)
    record("T6 contracts igual ao de antes fora das colunas novas (contagem + md5)",
           tuple(await c.fetchrow(CONTRACTS_FP_SQL)) == before["contracts_fp"])
    record("T6b proposals igual ao de antes fora das colunas novas (contagem + md5)",
           tuple(await c.fetchrow(PROPOSALS_FP_SQL)) == before["proposals_fp"])
    for t in ("contracts", "proposals"):
        await check_row(c, f"T7 {t}.billing_interval_months: integer, not null, default 1",
                        "select data_type::text, is_nullable::text, column_default::text from information_schema.columns "
                        "where table_schema = 'public' and table_name = $1 and column_name = 'billing_interval_months'",
                        ("integer", "NO", "1"), t)
        await check(c, f"T8 {t}: check billing_interval_months in (1, 2, 3, 4, 6, 12) existe",
                    "select count(*) from pg_constraint where conname = $1 and contype = 'c'", 1,
                    f"{t}_billing_interval_months_valid")
    await check(c, "T9 todas as linhas existentes ficaram com intervalo 1 (contracts + proposals)",
                "select (select count(*) from public.contracts where billing_interval_months <> 1) + "
                "(select count(*) from public.proposals where billing_interval_months <> 1)", 0)
    await check_row(c, "T10 contracts.termination_notice_date: date, aceita nulo",
                    "select data_type::text, is_nullable::text from information_schema.columns where table_schema = "
                    "'public' and table_name = 'contracts' and column_name = 'termination_notice_date'", ("date", "YES"))
    await check_row(c, "T10b contracts.termination_reason: text, aceita nulo",
                    "select data_type::text, is_nullable::text from information_schema.columns where table_schema = "
                    "'public' and table_name = 'contracts' and column_name = 'termination_reason'", ("text", "YES"))
    await check(c, "T11 nenhum contrato existente com dados de encerramento preenchidos",
                "select count(*) from public.contracts where termination_notice_date is not null "
                "or termination_reason is not null", 0)

    # close_deal de ponta a ponta DEPOIS da 049
    cd_after = await close_deal_flow(c, cd_user, check_first_due=True)
    record("CD1 close_deal depois da 049 executa sem erro", "FALHOU" not in cd_after, str(cd_after))
    record("CD2 depois: contrato criado", cd_after.get("contrato_criado") is True, str(cd_after))
    record("CD3 depois: proposta aceita", cd_after.get("proposta_status") == "aceita", str(cd_after))
    record("CD4 depois: projeto fechado_ganho", cd_after.get("projeto_estagio") == "fechado_ganho", str(cd_after))
    record("CD5 depois: SPE criada", cd_after.get("spe_criada") is True, str(cd_after))
    after_cmp = {k: v for k, v in cd_after.items() if k != "first_due_date_nulo"}
    record("CD6 resultado do fechamento igual antes e depois da 049", after_cmp == cd_before,
           f"antes {cd_before}, depois {after_cmp}")
    record("CD7 contracts.first_due_date fica nulo no contrato criado pelo close_deal",
           cd_after.get("first_due_date_nulo") is True, str(cd_after))

    today = await c.fetchval("select current_date")
    horizon = add_months(datetime.date(today.year, today.month, 1), 13) - datetime.timedelta(days=1)

    # ---------- dados de apoio (dono da migration) ----------
    fin = await make_user(c, "fin")
    crm = await make_user(c, "crm")
    none_ = await make_user(c, "sem")
    # master de teste: financeiro + system_role = 'master', trocado como dono
    # (sem usuário logado, o trigger da 043 permite); some no rollback
    mst = await make_user(c, "mst")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro')", mst)
    await c.execute("update public.profiles set system_role = 'master' where id = $1", mst)
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro'), ($2, 'crm')",
                    fin, crm)
    # encerramento exige escrita em contratos (crm) e em parcelas (financeiro)
    full = await make_user(c, "full")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro'), ($1, 'crm')",
                    full)
    project = await c.fetchval("insert into public.projects (name, owner_id) values ($1::text, $2) returning id",
                               f"TESTE 049 {TAG}", fin)
    codes = itertools.count(1)
    st = {r["code"]: r["id"] for r in await c.fetch("select id, code from public.service_types")}
    team_a = await c.fetchval("insert into public.teams (name) values ($1::text) returning id", f"TESTE 049 A {TAG}")
    team_b = await c.fetchval("insert into public.teams (name) values ($1::text) returning id", f"TESTE 049 B {TAG}")

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
                       status="ativo", svc="SVC-002", split="2025-01-01", term=None, interval=1):
        cid = await c.fetchval(
            """insert into public.contracts (project_id, contract_code, contract_label, service_type_id,
                 payment_type, fee_value, readjustment_index, readjustment_cycle_months, start_date,
                 first_due_date, end_date, status, term_months, billing_interval_months)
               values ($1, $2::text, 'TESTE 049', $3, $4::text, $5::numeric, $6::text, $7::int,
                       ($8::text)::date, ($9::text)::date, ($10::text)::date, $11::text, $12::int, $13::int)
               returning id""",
            project, f"{next(codes):02d}", st[svc], payment_type, str(fee), index, cycle,
            start, first_due, end, status, term, interval)
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
        "values ($1, $2::text, '2026-08-01', 10, $3) returning id", cat, f"TESTE 049 {TAG}", fin)

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
    await expect_fail(c, "B9 parcelado sem term_months recusado (22023 na 049; era 0A000)", lambda: gen(parc), "22023")
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
    await expect_fail(c, "V3c financeiro não master com p_allow_retroactive = true: 42501 (048)",
                      lambda: set_split_imm(fin, rt, "2026-07-01", p_b, True), "42501")
    await expect_ok(c, "V3c2 a mesma versão passa com p_allow_retroactive = true pelo master",
                    lambda: set_split_imm(mst, rt, "2026-07-01", p_b, True))
    await expect_ok(c, "V3d versão de set/2026 passa: a emitida de ago fica fora da janela",
                    lambda: set_split_imm(fin, rt, "2026-09-01", p_b))
    await c.execute("update public.contract_installments set status = 'recebida', received_date = due_date, "
                    "received_amount = expected_amount where contract_id = $1 and due_date = '2026-10-10'", rt)
    await expect_fail(c, "V3e regravar set/2026 igual é recusado: recebida em out na janela (checagem conservadora)",
                      lambda: set_split_imm(fin, rt, "2026-09-01", p_b), "55000")
    await expect_fail(c, "V4 remover jul/2026 é recusado: a janela (jul a ago) tem a emitida de ago",
                      lambda: set_split_imm(fin, rt, "2026-07-01", "[]"), "55000")
    await expect_fail(c, "V4b financeiro não master removendo jul/2026 com retroativo: 42501 (048)",
                      lambda: set_split_imm(fin, rt, "2026-07-01", "[]", True), "42501")
    await expect_ok(c, "V4b2 remover jul/2026 com p_allow_retroactive pelo master passa (jan/2026 continua cobrindo)",
                    lambda: set_split_imm(mst, rt, "2026-07-01", "[]", True))
    await expect_fail(c, "V4c financeiro não master removendo jan/2026 com retroativo: 42501 (048)",
                      lambda: set_split_imm(fin, rt, "2026-01-01", "[]", True), "42501")
    await expect_fail(c, "V4c2 master removendo jan/2026 com retroativo: deixaria parcelas de jan a ago sem regra",
                      lambda: set_split_imm(mst, rt, "2026-01-01", "[]", True), "55000")
    ov = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    await expect_ok(c, "V4d setup: gera parcelas com a única versão (jan/2025)", lambda: gen(ov))
    await expect_fail(c, "V4e financeiro não master removendo a única versão com retroativo: 42501 (048)",
                      lambda: set_split_imm(fin, ov, "2025-01-01", "[]", True), "42501")
    await expect_fail(c, "V4e2 master removendo a única versão de contrato com parcelas é recusado",
                      lambda: set_split_imm(mst, ov, "2025-01-01", "[]", True), "55000")
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

    # ---------- (r) master e (n) financeiro não master ----------
    rn = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", split="2026-01-01")

    async def rn_setup():
        await gen(rn)
        await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                        "where contract_id = $1 and due_date = '2026-08-10'", rn)
    await expect_ok(c, "R0 setup: 12 parcelas com versão de jan/2026 e a de ago/2026 emitida", rn_setup)
    await expect_ok(c, "R1 master: versão de jul/2026 com retroativo (emitida de ago na janela) é aceita",
                    lambda: set_split_imm(mst, rn, "2026-07-01", p_b, True))
    await expect_ok(c, "R2 master: remover jul/2026 com retroativo, com jan/2026 ainda cobrindo, é aceito",
                    lambda: set_split_imm(mst, rn, "2026-07-01", "[]", True))
    await expect_fail(c, "R3 master: remover jan/2026 com retroativo deixaria parcelas sem regra (55000)",
                      lambda: set_split_imm(mst, rn, "2026-01-01", "[]", True), "55000")
    await expect_fail(c, "R4 master: versão de jul/2026 sem retroativo com a emitida na janela (55000, igual à 047)",
                      lambda: set_split_imm(mst, rn, "2026-07-01", p_b), "55000")
    await expect_fail(c, "N1 financeiro não master: jul/2026 com retroativo e emitida na janela é 42501, não 55000",
                      lambda: set_split_imm(fin, rn, "2026-07-01", p_b, True), "42501")
    await expect_fail(c, "N2 financeiro não master: retroativo numa janela sem parcela travada também é 42501",
                      lambda: set_split_imm(fin, rn, "2026-09-01", p_b, True), "42501")
    await expect_ok(c, "N3 financeiro não master: versão nova sem retroativo (set/2026, janela livre) é aceita",
                    lambda: set_split_imm(fin, rn, "2026-09-01", p_b))
    await expect_fail(c, "N4 financeiro não master: jul/2026 sem retroativo com a emitida na janela (55000)",
                      lambda: set_split_imm(fin, rn, "2026-07-01", p_b), "55000")
    await expect_ok(c, "N5 financeiro não master: remover set/2026 sem retroativo, com cobertura, é aceito",
                    lambda: set_split_imm(fin, rn, "2026-09-01", "[]"))
    await expect_fail(c, "N6a financeiro não master: soma 90 continua 23514",
                      lambda: set_split_imm(fin, rn, "2026-11-01",
                                            splits(("dono", team_a, "g", 70), ("a_parte", None, "p", 20))), "23514")
    await expect_fail(c, "N6b financeiro não master: percentual com 3 casas continua 22023",
                      lambda: set_split_imm(fin, rn, "2026-11-01",
                                            splits(("dono", team_a, "g", 33.333), ("a_parte", None, "p", 66.667))),
                      "22023")
    await expect_fail(c, "N6c financeiro não master: dono sem team_id continua 22023",
                      lambda: set_split_imm(fin, rn, "2026-11-01", splits(("dono", None, "g", 100))), "22023")

    # ---------- (p) permissões ----------
    await expect_fail(c, "P1 crm com retroativo é recusado (42501, pela permissão)",
                      lambda: set_split_imm(crm, rn, "2026-11-01", p_b, True), "42501")

    async def retro_without_sub():
        await as_authenticated_no_sub(c)
        await c.fetchval(SPLITS, rn, "2026-11-01", p_b, True)
    await expect_fail(c, "P2 sem auth.uid() com retroativo é recusado (42501)", retro_without_sub, "42501")

    async def retro_as_anon():
        await as_anon(c)
        await c.fetchval(SPLITS, rn, "2026-11-01", p_b, True)
    await expect_fail(c, "P3 anon não executa set_contract_splits", retro_as_anon, "42501")

    # ---------- (s2) estrutura da 048 ----------
    await check(c, "S1 assinatura inalterada: uma única set_contract_splits(uuid, date, jsonb, boolean)",
                "select count(*) = 1 and bool_and(oid = to_regprocedure($1::text)) from pg_proc "
                "where proname = 'set_contract_splits' and pronamespace = 'public'::regnamespace", True, NEW_SPLITS)
    await check(c, "S2 security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, NEW_SPLITS)
    await check(c, "S3a anon sem EXECUTE (como na 047)",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, NEW_SPLITS)
    await check(c, "S3b PUBLIC sem EXECUTE (como na 047)",
                "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                "where p.oid = to_regprocedure($1::text) and a.grantee = 0", 0, NEW_SPLITS)
    await check(c, "S3c authenticated com EXECUTE (como na 047)",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, NEW_SPLITS)

    await check(c, "S4 set_contract_splits com o corpo da 048 inalterado pela 049 (md5)",
                f"select md5(({SPLITS_DEF_SQL}))", before["splits_def_md5"])
    await check(c, "S5 is_master() inalterada", IS_MASTER_MD5_SQL, before["is_master"])

    # ---------- (q) geração com prazo (term_months) ----------
    async def n_inst(cid, where="true"):
        return await c.fetchval(f"select count(*) from public.contract_installments where contract_id = $1 and {where}",
                                cid)

    q36 = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=36)
    n = await expect_ok(c, "Q1 mensal com prazo de 36 meses: gera", lambda: gen(q36))
    record("Q1b gera 36 parcelas de uma vez (passando do horizonte de 12)", n == 36, f"veio {n!r}")
    await check_row(c, "Q1c primeiro e último vencimento (2026-01-10 a 2028-12-10)",
                    "select min(due_date)::text, max(due_date)::text from public.contract_installments "
                    "where contract_id = $1", ("2026-01-10", "2028-12-10"), q36)
    qend = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=36, end="2026-06-30")
    n = await expect_ok(c, "Q2 mensal com prazo de 36 e end_date em jun/2026: gera", lambda: gen(qend))
    record("Q2b o end_date limita: 6 parcelas (jan a jun)", n == 6, f"veio {n!r}")
    qnt = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")
    n = await expect_ok(c, "Q3 mensal sem prazo: gera", lambda: gen(qnt))
    record("Q3b sem prazo continua gerando 12 (como antes)", n == 12, f"veio {n!r}")
    qp6 = await contract("parcelado", 1500, "2026-01-01", "2026-03-05", term=6)
    n = await expect_ok(c, "Q4 parcelado com prazo de 6: gera", lambda: gen(qp6))
    record("Q4b parcelado com prazo de 6 gera 6 parcelas", n == 6, f"veio {n!r}")
    await check_row(c, "Q4c cada parcela do parcelado vale fee_value (valor de cada parcela), sem reajuste",
                    "select count(*), min(base_amount), max(base_amount), bool_and(expected_amount = base_amount) "
                    "from public.contract_installments where contract_id = $1", (6, Decimal("1500"), Decimal("1500"), True),
                    qp6)
    qpe = await contract("parcelado", 1500, "2026-01-01", "2026-03-05", term=6, end="2026-05-31")
    n = await expect_ok(c, "Q5 parcelado com prazo de 6 e end_date em mai/2026: gera", lambda: gen(qpe))
    record("Q5b o end_date limita também o parcelado: 3 parcelas (mar a mai)", n == 3, f"veio {n!r}")
    await expect_fail(c, "Q6 term_months = 0 é recusado pelo check",
                      lambda: contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=0, split=None),
                      "23514")
    await expect_fail(c, "Q6b proposals.term_months = -1 é recusado pelo check",
                      lambda: c.execute("insert into public.proposals (project_id, value, payment_type, term_months) "
                                        "values ($1, 100, 'mensal_recorrente', -1)", project), "23514")

    # ---------- (i) intervalo de cobrança (billing_interval_months) ----------
    ib = await contract("mensal_recorrente", 2000, "2026-01-01", "2026-01-10", term=12, interval=2)
    n = await expect_ok(c, "I1 bimestral com prazo de 12: gera", lambda: gen(ib))
    record("I1b gera 12 / 2 = 6 parcelas", n == 6, f"veio {n!r}")
    await check(c, "I1c vencimentos de 2 em 2 meses a partir do primeiro", "select string_agg(due_date::text, ',' "
                "order by due_date) from public.contract_installments where contract_id = $1",
                "2026-01-10,2026-03-10,2026-05-10,2026-07-10,2026-09-10,2026-11-10", ib)
    it = await contract("mensal_recorrente", 3000, "2026-01-01", "2026-01-10", interval=3)
    n = await expect_ok(c, "I2 trimestral sem prazo: gera", lambda: gen(it))
    record("I2b sem prazo gera um ano: 12 / 3 = 4 parcelas", n == 4, f"veio {n!r}")
    await check(c, "I2c vencimentos de 3 em 3 meses", "select string_agg(due_date::text, ',' order by due_date) "
                "from public.contract_installments where contract_id = $1",
                "2026-01-10,2026-04-10,2026-07-10,2026-10-10", it)
    i10 = await contract("mensal_recorrente", 3000, "2026-01-01", "2026-01-10", term=10, interval=3)
    await expect_fail(c, "I3 prazo 10 com intervalo 3 (não múltiplo): geração recusa", lambda: gen(i10), "22023")
    await expect_fail(c, "I4 contracts.billing_interval_months = 5 é recusado pelo check",
                      lambda: contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", interval=5, split=None),
                      "23514")
    await expect_fail(c, "I4b proposals.billing_interval_months = 5 é recusado pelo check",
                      lambda: c.execute("insert into public.proposals (project_id, value, payment_type, "
                                        "billing_interval_months) values ($1, 100, 'mensal_recorrente', 5)", project),
                      "23514")
    i12 = await contract("mensal_recorrente", 12000, "2026-01-01", "2026-01-10", interval=12)
    n = await expect_ok(c, "I5 anual sem prazo: gera", lambda: gen(i12))
    record("I5b anual sem prazo gera 1 parcela", n == 1, f"veio {n!r}")
    iu = await contract("parcela_unica", 5000, "2026-01-01", "2026-01-10", interval=3)
    n = await expect_ok(c, "I6 parcela_unica com intervalo 3: gera", lambda: gen(iu))
    record("I6b parcela_unica ignora o intervalo: 1 parcela", n == 1, f"veio {n!r}")
    ie = await contract("mensal_recorrente", 2000, "2026-01-01", "2026-01-10", term=24, interval=2, end="2026-06-30")
    n = await expect_ok(c, "I7 bimestral com prazo 24 e end_date em jun/2026: gera", lambda: gen(ie))
    record("I7b o end_date limita: 3 parcelas (jan, mar, mai)", n == 3, f"veio {n!r}")

    # extensão com intervalo: trimestral sem prazo, gera 4, define prazo de 18 (6 parcelas) e estende
    ix = await contract("mensal_recorrente", 3000, "2026-01-01", "2026-01-10", interval=3)

    async def ix_setup():
        await gen(ix)
        await c.execute("update public.contracts set term_months = 18 where id = $1", ix)
    await expect_ok(c, "IE1 setup: trimestral gera 4 e depois recebe prazo de 18 meses", ix_setup)
    n = await expect_ok(c, "IE2 extensão do trimestral", lambda: run_as(fin, EXT, ix))
    record("IE2b cria 2 (18 / 3 = 6 no total)", n == 2 and await n_inst(ix) == 6, f"veio {n!r}")
    await check(c, "IE2c vencimentos estendidos de 3 em 3 meses (jan e abr/2027)",
                "select string_agg(due_date::text, ',' order by due_date) from public.contract_installments "
                "where contract_id = $1", "2026-01-10,2026-04-10,2026-07-10,2026-10-10,2027-01-10,2027-04-10", ix)
    await check(c, "IE2d ponto de revisão pelo mesmo passo: só 2027-01-10 depois da 1ª parcela (ciclo de 12 do início)",
                "select string_agg(due_date::text, ',' order by due_date) from public.contract_installments "
                "where contract_id = $1 and is_revision_point and due_date > '2026-01-10'", "2027-01-10", ix)
    n = await expect_ok(c, "IE3 segunda extensão do trimestral", lambda: run_as(fin, EXT, ix))
    record("IE3b segunda extensão cria 0", n == 0, f"veio {n!r}")
    im = await contract("mensal_recorrente", 3000, "2026-01-01", "2026-01-10", term=12, interval=3)

    async def im_setup():
        await gen(im)
        await c.execute("update public.contracts set term_months = 13 where id = $1", im)
    await expect_ok(c, "IE4 setup: trimestral com prazo 12 gera 4 e o prazo é editado para 13", im_setup)
    await expect_fail(c, "IE4b extensão recusa prazo editado que não é múltiplo do intervalo",
                      lambda: run_as(fin, EXT, im), "22023")

    # ---------- (xt) extensão com prazo ----------
    n = await expect_ok(c, "XT1 extensão de contrato com prazo já todo gerado", lambda: run_as(fin, EXT, q36))
    record("XT1b devolve 0 e não passa do prazo (continua com 36)", n == 0 and await n_inst(q36) == 36,
           f"veio {n!r}")
    qx = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10")

    async def gen_then_set_term():
        await gen(qx)
        await c.execute("update public.contracts set term_months = 15 where id = $1", qx)
    await expect_ok(c, "XT2 setup: gera 12 sem prazo e depois define prazo de 15", gen_then_set_term)
    n = await expect_ok(c, "XT2b extensão completa só até o prazo", lambda: run_as(fin, EXT, qx))
    record("XT2c cria 3 (13 a 15) e para em 15 parcelas", n == 3 and await n_inst(qx) == 15, f"veio {n!r}")
    n = await expect_ok(c, "XT2d segunda extensão", lambda: run_as(fin, EXT, qx))
    record("XT2e segunda extensão cria 0 (idempotente)", n == 0, f"veio {n!r}")
    n = await expect_ok(c, "XT3 parcelado agora é aceito pela extensão", lambda: run_as(fin, EXT, qp6))
    record("XT3b parcelado com prazo todo gerado: extensão devolve 0", n == 0, f"veio {n!r}")

    # ---------- (x) encerramento ----------
    # a função recebe a data do AVISO; a data final é sempre aviso + 30 dias
    CLOSE = "select * from public.close_contract($1::uuid, ($2::text)::date, $3::text)"

    async def close_as(uid, cid, notice, reason=None):
        await as_user(c, uid)
        row = await c.fetchrow(CLOSE, cid, notice, reason)
        await as_owner(c)
        return tuple(row)

    xc = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12)

    async def xc_setup():
        await gen(xc)
        await avulsa(xc, 90, "2026-11-20")
        await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                        "where contract_id = $1 and due_date = '2026-03-10'", xc)
    await expect_ok(c, "X0 setup: 12 parcelas, emitida em mar/2026 e uma avulsa projetada em nov/2026", xc_setup)
    await expect_fail(c, "X1 só financeiro (sem escrita em contratos) não encerra", lambda: close_as(fin, xc, "2026-05-31"),
                      "42501")
    await expect_fail(c, "X2 só crm (sem escrita em parcelas) não encerra", lambda: close_as(crm, xc, "2026-05-31"),
                      "42501")
    r = await expect_ok(c, "X3 crm + financeiro encerra com aviso em 2026-05-31 e motivo com espaços",
                        lambda: close_as(full, xc, "2026-05-31", "  rescisão amigável  "))
    record("X3b devolve 6 projetadas canceladas (jul a dez) e 1 avulsa em aberto", r == (6, 1), f"veio {r!r}")
    await check_row(c, "X3c encerrado; end_date = aviso + 30 = 2026-06-30; aviso gravado; motivo sem espaços nas pontas",
                    "select status, end_date::text, termination_notice_date::text, termination_reason "
                    "from public.contracts where id = $1",
                    ("encerrado", "2026-06-30", "2026-05-31", "rescisão amigável"), xc)
    await check_row(c, "X3d parcelas: 6 canceladas depois de jun; 5 projetadas e 1 emitida até jun; avulsa projetada",
                    "select count(*) filter (where origin = 'projetada' and status = 'cancelada' and due_date > '2026-06-30'), "
                    "count(*) filter (where origin = 'projetada' and status = 'projetada' and due_date <= '2026-06-30'), "
                    "count(*) filter (where status = 'emitida'), "
                    "count(*) filter (where origin = 'avulsa' and status = 'projetada') "
                    "from public.contract_installments where contract_id = $1", (6, 5, 1, 1), xc)
    await check(c, "X3e marca app.closing_contract limpa depois da função",
                "select coalesce(current_setting('app.closing_contract', true), '')", "")
    await expect_fail(c, "X4 encerrar de novo é recusado", lambda: close_as(full, xc, "2026-05-31"), "55000")
    await expect_fail(c, "X5 depois de encerrado, a extensão recusa o contrato", lambda: run_as(fin, EXT, xc), "55000")
    xd = await contract("mensal_recorrente", 1000, "2026-03-01", "2026-03-10", term=12)
    await expect_fail(c, "X6 aviso em 2026-01-15 (final 2026-02-14) anterior ao início (2026-03-01) é recusado",
                      lambda: close_as(full, xd, "2026-01-15"), "22023")
    await expect_fail(c, "X7 data do aviso nula é recusada",
                      lambda: run_as(full, "select * from public.close_contract($1::uuid, null)", xd), "22004")
    xe = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12)

    async def xe_setup():
        await gen(xe)
        await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                        "where contract_id = $1 and due_date = '2026-09-10'", xe)
    await expect_ok(c, "X8 setup: parcela emitida em set/2026", xe_setup)
    await expect_fail(c, "X8b aviso em 2026-05-31 (final jun/2026) com emitida em set/2026 é recusado",
                      lambda: close_as(full, xe, "2026-05-31"), "55000")
    await check_row(c, "X8c nada mudou: contrato ativo e nenhuma parcela cancelada",
                    "select (select status from public.contracts where id = $1), "
                    "(select count(*) from public.contract_installments where contract_id = $1 and status = 'cancelada')",
                    ("ativo", 0), xe)

    async def close_without_sub():
        await as_authenticated_no_sub(c)
        await c.fetchrow(CLOSE, xd, "2026-05-31", None)
    await expect_fail(c, "X9 sem auth.uid() é recusado", close_without_sub, "42501")
    xs = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12, status="suspenso",
                        split=None)
    r = await expect_ok(c, "X10 contrato suspenso pode ser encerrado (motivo só com espaços)",
                        lambda: close_as(full, xs, "2026-05-31", "   "))
    record("X10b sem parcelas geradas: devolve 0 e 0", r == (0, 0), f"veio {r!r}")
    await check(c, "X10c motivo só com espaços gravado como nulo",
                "select termination_reason is null from public.contracts where id = $1", True, xs)

    # ---------- (av) aviso prévio de 30 dias ----------
    xb = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12)

    async def xb_setup():
        await gen(xb)
        await c.execute("update public.contract_installments set status = 'emitida', issue_date = due_date "
                        "where contract_id = $1 and due_date = '2026-07-10'", xb)
    await expect_ok(c, "AV1 setup: 12 parcelas e emitida em 2026-07-10", xb_setup)
    r = await expect_ok(c, "AV2 aviso em 2026-06-10: final 2026-07-10, igual ao vencimento da emitida, é aceito",
                        lambda: close_as(full, xb, "2026-06-10", ""))
    record("AV2b cancela só ago a dez (5); a do próprio dia final fica", r == (5, 0), f"veio {r!r}")
    await check_row(c, "AV2c end_date 2026-07-10, parcela de 2026-07-10 continua emitida, motivo vazio gravado como nulo",
                    "select (select end_date::text from public.contracts where id = $1), "
                    "(select status from public.contract_installments where contract_id = $1 "
                    "and due_date = '2026-07-10'), "
                    "(select termination_reason is null from public.contracts where id = $1)",
                    ("2026-07-10", "emitida", True), xb)
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    xf = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12, split=None)
    await expect_fail(c, "AV3 aviso com data futura (amanhã) é recusado", lambda: close_as(full, xf, tomorrow), "22023")
    await check(c, "AV3b contrato continua ativo depois da recusa",
                "select status from public.contracts where id = $1", "ativo", xf)
    r = await expect_ok(c, "AV4 aviso com a data de hoje é aceito (sem motivo, pelo default)",
                        lambda: run_as(full, "select (public.close_contract($1::uuid, current_date)).cancelled_installments",
                                       xf))
    await check_row(c, "AV4b end_date = hoje + 30, aviso = hoje, motivo nulo",
                    "select end_date = current_date + 30, termination_notice_date = current_date, "
                    "termination_reason is null from public.contracts where id = $1", (True, True, True), xf)

    # ---------- (z) trigger: encerrar só pela close_contract ----------
    zc = await contract("mensal_recorrente", 1000, "2026-01-01", "2026-01-10", term=12)

    async def direct_close_as(uid):
        await as_user(c, uid)
        await c.execute("update public.contracts set status = 'encerrado' where id = $1", zc)
    await expect_fail(c, "Z1 crm encerrando direto na tabela é recusado pelo trigger", lambda: direct_close_as(crm), "42501")
    await expect_fail(c, "Z1b crm + financeiro encerrando direto na tabela também é recusado",
                      lambda: direct_close_as(full), "42501")

    async def direct_suspend_as_crm():
        await as_user(c, crm)
        status = await c.execute("update public.contracts set status = 'suspenso' where id = $1", zc)
        await as_owner(c)
        assert status == "UPDATE 1", f"update do crm: {status}"
    await expect_ok(c, "Z2 crm pode mudar para suspenso direto (o trigger só barra 'encerrado')", direct_suspend_as_crm)

    async def spoof_other_contract():
        await as_user(c, crm)
        await c.fetchval("select set_config('app.closing_contract', $1::text, true)", str(xc))
        await c.execute("update public.contracts set status = 'encerrado' where id = $1", zc)
    await expect_fail(c, "Z3 marca de outro contrato não libera este", spoof_other_contract, "42501")
    await expect_ok(c, "Z4 como dono (sem usuário logado) o trigger não barra",
                    lambda: c.execute("update public.contracts set status = 'encerrado' where id = $1", zc))

    # reabertura: de 'encerrado' para outro status pela API é recusado
    async def direct_set_as(uid, status):
        await as_user(c, uid)
        res = await c.execute("update public.contracts set status = $2::text where id = $1", zc, status)
        await as_owner(c)
        assert res == "UPDATE 1", f"update: {res}"
    await expect_fail(c, "Z7 crm reabrindo (encerrado -> ativo) direto na tabela é recusado",
                      lambda: direct_set_as(crm, "ativo"), "42501")
    await expect_fail(c, "Z7b crm + financeiro mudando encerrado -> suspenso também é recusado",
                      lambda: direct_set_as(full, "suspenso"), "42501")
    await expect_ok(c, "Z8 crm regravando 'encerrado' sobre 'encerrado' passa (não é reabertura)",
                    lambda: direct_set_as(crm, "encerrado"))
    await expect_ok(c, "Z9 como dono (sem usuário logado) reabrir não é barrado",
                    lambda: c.execute("update public.contracts set status = 'ativo' where id = $1", zc))
    await check(c, "Z9b contrato reaberto pelo dono ficou ativo",
                "select status from public.contracts where id = $1", "ativo", zc)

    async def reopen_xc_as_crm():
        await as_user(c, crm)
        await c.execute("update public.contracts set status = 'ativo' where id = $1", xc)
    await expect_fail(c, "Z10 contrato encerrado pela close_contract também não reabre pela API (crm)",
                      reopen_xc_as_crm, "42501")
    for role in ("anon", "authenticated"):
        await check(c, f"Z5 {role} sem EXECUTE na função do trigger",
                    "select has_function_privilege($1::name, $2::text, 'execute')", False, role, GUARD_FN)
    await check(c, "Z6 trigger trg_contracts_guard_close é BEFORE UPDATE OF status",
                "select pg_get_triggerdef(oid) like '%BEFORE UPDATE OF status ON public.contracts%' "
                "from pg_trigger where tgname = 'trg_contracts_guard_close'", True)

    # ---------- (k) estrutura de close_contract ----------
    await check(c, "K1 close_contract: security definer e search_path vazio",
                "select prosecdef and coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                "from pg_proc where oid = to_regprocedure($1::text)", True, CLOSE_FN)
    await check(c, "K2 anon sem EXECUTE em close_contract",
                "select has_function_privilege('anon'::name, $1::text, 'execute')", False, CLOSE_FN)
    await check(c, "K3 PUBLIC sem EXECUTE em close_contract",
                "select count(*) from pg_proc p, aclexplode(p.proacl) a "
                "where p.oid = to_regprocedure($1::text) and a.grantee = 0", 0, CLOSE_FN)
    await check(c, "K4 authenticated com EXECUTE em close_contract",
                "select has_function_privilege('authenticated'::name, $1::text, 'execute')", True, CLOSE_FN)
    await check(c, "K5 argumentos: aviso e motivo, sem parâmetro de data final",
                "select pg_get_function_arguments(to_regprocedure($1::text))",
                "p_contract_id uuid, p_notice_date date, p_reason text DEFAULT NULL::text", CLOSE_FN)
    await check(c, "K6 só uma close_contract (a assinatura (uuid, date) não existe)",
                "select count(*) = 1 and to_regprocedure($1::text) is null from pg_proc "
                "where proname = 'close_contract' and pronamespace = 'public'::regnamespace", True, OLD_CLOSE_FN)
    await check(c, "K7 função do trigger contém a regra de reabertura",
                "select prosrc like '%não pode ser reaberto%' from pg_proc where oid = to_regprocedure($1::text)",
                True, GUARD_FN)


async def post_check(dsn, before, fp_before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("prod"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 colunas novas da 049 ausentes (term_months, billing_interval_months, termination_*)",
                        "select count(*) from information_schema.columns where table_schema = 'public' "
                        "and table_name in ('contracts', 'proposals') and column_name in ('term_months', "
                        "'billing_interval_months', 'termination_notice_date', 'termination_reason')", 0)
            await check(c2, "L2 close_contract, função e trigger de guarda ausentes",
                        "select (select count(*) from pg_proc where proname in ('close_contract', 'fn_contracts_guard_close')) "
                        "+ (select count(*) from pg_trigger where tgname = 'trg_contracts_guard_close')", 0)
            await check(c2, "L3 generate/extend de volta ao corpo de antes (md5)", GEN_EXT_MD5_SQL, before["genext"])
            await check(c2, "L4 set_contract_splits igual ao de antes (md5)",
                        f"select md5(({SPLITS_DEF_SQL}))", before["splits_def_md5"])
            await check(c2, "L5 close_deal igual ao de antes do teste", CLOSE_DEAL_MD5_SQL, before["close_deal"])
            await check(c2, "L6 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            await check(c2, "L7 nenhum projeto, time ou transação de teste",
                        "select (select count(*) from public.projects where name like 'TESTE 049%') + "
                        "(select count(*) from public.teams where name like 'TESTE 049%') + "
                        "(select count(*) from public.bank_transactions where external_id like 'teste049-%')", 0)
            record("L8 contracts e proposals iguais aos de antes do teste (contagem + md5)",
                   tuple(await c2.fetchrow(CONTRACTS_FP_SQL)) == before["contracts_fp"]
                   and tuple(await c2.fetchrow(PROPOSALS_FP_SQL)) == before["proposals_fp"])
            await check(c2, "L9 comentários de installments_count iguais aos de antes do teste", IC_COMMENTS_SQL,
                        before["ic_comments"])
            diego = before["diego"]
            for key, table, expr in REAL_TABLES:
                now = await table_fp(c2, table, expr)
                b = fp_before[key]
                record(f"L10 {key}: tabela inteira igual ao começo (contagem + md5)", now == b,
                       f"antes {fmt(b)}, depois {fmt(now)}")
            record("L11 perfil e módulos do Diego iguais ao começo (md5)",
                   await diego_fp(c2, diego) == fp_before["diego"])
            m = await master_ids(c2)
            record("L12 masters = 1 e é o Diego", m == [diego], f"{len(m)} master(s)")
            for t in EXTRA_TABLES:
                await check(c2, f"L13 {t}: contagem igual ao começo", f"select count(*) from public.{t}",
                            fp_before["extra_counts"][t])
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
        ids, fp_before = await measure_before(c, before["diego"])
        await run_tests(c, sql, before)
        await real_data_in_txn(c, ids, fp_before, before["diego"])
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
