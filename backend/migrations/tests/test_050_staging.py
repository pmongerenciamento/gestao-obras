"""Teste da migration 050 no STAGING (que já tem da 043 à 049 aplicadas),
tudo numa transação desfeita.

Uso (do repositório):
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/migrations/tests/test_050_staging.py

A 050 é aplicada dentro da transação e, sobre ela, rodam: H (close_deal com o
mesmo md5) e E (tabelas existentes com as mesmas colunas); S (estrutura e
privilégios das 5 tabelas e das 3 funções); D (seeds e catálogo); C (checks,
dono único e unicidade de e-mail); B (created_by); P (permissões por tabela:
financeiro, crm, sem módulo e anon); R (master sem módulo no regime); G
(trava do regime). O master de teste é criado dentro da transação
(system_role trocado como dono, sem usuário logado, o que o trigger da 043
permite), SEM nenhum módulo, e some no rollback.

Regras:
- Só roda com DATABASE_URL de backend/.env.staging com us-west-2 e a ref de
  staging, sem a ref de produção (checado antes de qualquer conexão).
- Aborta se server_version_num < 150000, se a 049 não estiver aplicada
  (contracts.term_months ou close_contract ausente), se a 050 já estiver
  (taxpayer_profiles ou qualquer das 5 tabelas existe) ou se faltar
  is_master(), has_permission() ou set_updated_at().
- Aplica a 050 e roda os testes numa transação só, desfeita no final
  (ROLLBACK sempre). Tentativas que devem falhar rodam em savepoints; SET
  LOCAL ROLE e set_config(..., true) dentro de um savepoint desfeito são
  desfeitos junto com ele. Os blocos R, G e B7 rodam em savepoints próprios,
  também desfeitos.
- As datas da trava do regime ficam em 2034-2046 (e 2024 no G14), longe de
  qualquer parcela real; o número de parcelas emitidas ou recebidas do
  staging é só impresso.
- Usuários fictícios @example.invalid; nada de e-mail, senha, chave ou DSN
  impresso. Nenhum commit.
- No fim, conexão nova READ ONLY confere que nada ficou para trás.

N esperado (calculado pelos rótulos e laços): 166 verificações
  M0 1 + H1 1 + E1 x 5 tabelas existentes = 5                          -> 7
  + (s) S1, S2, S3, S4 e S5 x 5 tabelas novas = 25
        S6 e S7 x 3 funções = 6                                         -> 31
  + (d) D1 a D6                                                         -> 6
  + (c) C1 a C6 6, C7 e C8 2, C9 1, C10 e C11 2, C12 x 5 retenções 5,
        C13 e C14 2, C15 a C17 3, C18 a C21 4, C22 1, C23 1, C24 e C25 2,
        C26 a C28 3, C29 1, C30 e C31 2, C32 a C36 5                    -> 40
  + (b) B1 a B7                                                         -> 7
  + (p) P1 a P9 x 5 tabelas novas                                       -> 45
  + (r) R1 a R5                                                         -> 5
  + (g) G0a a G0d 4, G1 a G6 6, G7 a G9 3, G10 e G11 2, G12, G13, G14  -> 18
  + pós-rollback L1 a L7                                                -> 7
  7 + 31 + 6 + 40 + 7 + 45 + 5 + 18 + 7 = 166
Se a M0 falhar, o script para logo depois: M0 + L1 a L7 = 8 verificações.
"""
import asyncio
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
MIGRATION = REPO / "backend" / "migrations" / "050_billing_registry.sql"
STAGING_REF = "gesqstdtbbdhlravddhd"
PROD_REF = "ttqtefwntkgpgatrcyps"
TAG = "teste050-" + secrets.token_hex(4)
OWNER = "owner"  # run_as sem papel: dono da migration, sem usuário logado
NEW_TABLES = ["taxpayer_profiles", "billing_contacts", "contract_fiscal_settings",
              "company_tax_regimes", "dre_tax_rates"]
NO_DELETE = {"taxpayer_profiles", "billing_contacts", "contract_fiscal_settings", "dre_tax_rates"}
NEW_FUNCS = ["public.fn_set_created_by()", "public.fn_tax_regime_locked_count(date, date)",
             "public.fn_company_tax_regimes_guard()"]
NEW_FUNC_NAMES = ["fn_set_created_by", "fn_tax_regime_locked_count", "fn_company_tax_regimes_guard"]
EXISTING_TABLES = ["contracts", "billing_entities", "clients", "proposals", "service_types"]
RETENTIONS = ["pis_withheld_pct", "cofins_withheld_pct", "csll_withheld_pct", "irrf_withheld_pct",
              "inss_withheld_pct"]
EXPECTED_PERMS = {
    ("financeiro", "taxpayer_profiles", True, True), ("crm", "taxpayer_profiles", True, False),
    ("financeiro", "billing_contacts", True, True), ("crm", "billing_contacts", True, False),
    ("financeiro", "contract_fiscal_settings", True, True), ("crm", "contract_fiscal_settings", True, False),
    ("financeiro", "company_tax_regimes", True, False), ("crm", "company_tax_regimes", True, False),
    ("financeiro", "dre_tax_rates", True, True),
}
CLOSE_DEAL_MD5_SQL = ("select md5(coalesce(string_agg(pg_get_functiondef(p.oid), '|' order by p.oid), '')) "
                      "from pg_proc p where p.proname = 'close_deal' and p.pronamespace = 'public'::regnamespace")
STRUCT_MD5_SQL = ("select md5(coalesce(string_agg(column_name::text || ':' || data_type::text || ':' || "
                  "is_nullable::text || ':' || coalesce(column_default::text, ''), ',' order by ordinal_position), '')) "
                  "from information_schema.columns where table_schema = 'public' and table_name = $1::text")

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


async def as_owner(c):
    await c.execute("reset role")
    await c.fetchval("select set_config('request.jwt.claim.sub', '', true), "
                     "set_config('request.jwt.claims', '', true)")


# ---------- helpers de teste ----------
async def check(c, name, sql, expected, *args):
    v = await c.fetchval(sql, *args)
    record(name, v == expected, f"esperado {expected!r}, veio {v!r}")


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
                            "and table_name = 'contracts' and column_name = 'term_months') "
                            "and to_regprocedure('public.close_contract(uuid, date, text)') is not null"):
        abort("a 049 não está aplicada (contracts.term_months ou close_contract ausente)")
    if await c.fetchval("select to_regclass('public.taxpayer_profiles') is not null"):
        abort("a 050 parece já aplicada (taxpayer_profiles existe)")
    for t in NEW_TABLES:
        if await c.fetchval("select to_regclass($1::text) is not null", f"public.{t}"):
            abort(f"a 050 parece já aplicada ({t} existe)")
    for fn in ("public.is_master()", "public.has_permission(text, text)", "public.set_updated_at()"):
        if not await c.fetchval("select to_regprocedure($1::text) is not null", fn):
            abort(f"{fn} não existe")
    locked = await c.fetchval("select count(*) from public.contract_installments "
                              "where status in ('emitida', 'recebida')")
    print(f"parcelas emitidas ou recebidas no staging (só informativo): {locked}")
    struct = {}
    for t in EXISTING_TABLES:
        struct[t] = await c.fetchval(STRUCT_MD5_SQL, t)
    return {"close_deal": await c.fetchval(CLOSE_DEAL_MD5_SQL), "struct": struct}


async def run_tests(c, sql, before):
    try:
        async with c.transaction():
            await c.execute(sql)
        record("M0 migration 050 aplica sem erro", True)
    except asyncpg.PostgresError as e:
        record("M0 migration 050 aplica sem erro", False, f"{e.sqlstate}: {str(e)[:300]}")
        return

    # ---------- (h) e (e) nada existente mudou ----------
    await check(c, "H1 close_deal com o mesmo md5 do corpo antes e depois da 050", CLOSE_DEAL_MD5_SQL,
                before["close_deal"])
    for t in EXISTING_TABLES:
        await check(c, f"E1 {t}: colunas iguais antes e depois da 050 (md5 da estrutura)", STRUCT_MD5_SQL,
                    before["struct"][t], t)

    # ---------- (s) estrutura e privilégios ----------
    for t in NEW_TABLES:
        rel = f"public.{t}"
        await check(c, f"S1 {t} existe", "select to_regclass($1::text) is not null", True, rel)
        await check(c, f"S2 {t}: RLS ligada",
                    "select relrowsecurity from pg_class where oid = ($1::text)::regclass", True, rel)
        await check(c, f"S3 {t}: anon sem nenhum privilégio",
                    "select bool_or(has_table_privilege('anon'::name, $1::text, p)) from unnest(array['SELECT', "
                    "'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p", False, rel)
        await check(c, f"S4 {t}: authenticated sem TRUNCATE",
                    "select has_table_privilege('authenticated'::name, $1::text, 'TRUNCATE')", False, rel)
        with_delete = t not in NO_DELETE
        await check(c, f"S5 {t}: authenticated {'com' if with_delete else 'sem'} DELETE",
                    "select has_table_privilege('authenticated'::name, $1::text, 'DELETE')", with_delete, rel)
    for fn in NEW_FUNCS:
        await check(c, f"S6 {fn}: authenticated sem EXECUTE",
                    "select has_function_privilege('authenticated'::name, $1::text, 'execute')", False, fn)
        await check(c, f"S7 {fn}: search_path vazio",
                    "select coalesce(array_to_string(proconfig, ','), '') = 'search_path=\"\"' "
                    "from pg_proc where oid = to_regprocedure($1::text)", True, fn)

    # ---------- (d) seeds e catálogo ----------
    rows = await c.fetch("select valid_from, regime, created_by from public.company_tax_regimes order by valid_from")
    got = [(r["valid_from"], r["regime"]) for r in rows]
    record("D1 company_tax_regimes: uma linha, 'simples' desde 2026-01-01",
           got == [(datetime.date(2026, 1, 1), "simples")], str(got))
    record("D2 seed do regime sem created_by", len(rows) == 1 and rows[0]["created_by"] is None)
    rows = await c.fetch("select month, rate, notes, created_by from public.dre_tax_rates order by month")
    got = [(r["month"], r["rate"]) for r in rows]
    record("D3 dre_tax_rates: 2026-06-01 e 2026-07-01 com 0,167",
           got == [(datetime.date(2026, 6, 1), Decimal("0.167")), (datetime.date(2026, 7, 1), Decimal("0.167"))],
           str(got))
    record("D4 seeds da taxa sem created_by e com a nota combinada",
           len(rows) == 2 and all(r["created_by"] is None and r["notes"] == "confirmado nos DRE de junho e julho"
                                  for r in rows))
    await check(c, "D5 catálogo: os 5 recursos novos",
                "select count(*) from public.resources where key = any($1::text[])", 5, NEW_TABLES)
    perms = {(r["module_code"], r["resource_key"], r["can_read"], r["can_write"]) for r in await c.fetch(
        "select module_code, resource_key, can_read, can_write from public.permissions "
        "where resource_key = any($1::text[])", NEW_TABLES)}
    record("D6 catálogo: exatamente as 9 permissões combinadas", perms == EXPECTED_PERMS, str(sorted(perms)))

    # ---------- dados de apoio (dono da migration) ----------
    fin = await make_user(c, "fin")
    crm = await make_user(c, "crm")
    none_ = await make_user(c, "sem")
    mst = await make_user(c, "mst")
    await c.execute("insert into public.profile_modules (profile_id, module) values ($1, 'financeiro'), ($2, 'crm')",
                    fin, crm)
    # master SEM módulo: system_role trocado como dono (sem usuário logado, o
    # trigger da 043 permite); some no rollback
    await c.execute("update public.profiles set system_role = 'master' where id = $1", mst)

    async def new_be(label):
        project = await c.fetchval("insert into public.projects (name, owner_id) values ($1::text, $2) returning id",
                                   f"TESTE 050 {label} {TAG}", fin)
        be = await c.fetchval("insert into public.billing_entities (project_id, legal_name, cnpj) "
                              "values ($1, $2::text, $3::text) returning id",
                              project, f"SPE TESTE 050 {label}",
                              "".join(secrets.choice("0123456789") for _ in range(14)))
        return project, be

    p1, be1 = await new_be("1")
    _, be2 = await new_be("2")
    _, be3 = await new_be("3")
    _, be4 = await new_be("4")
    svc = await c.fetchval("select id from public.service_types order by code limit 1")
    k1 = await c.fetchval(
        "insert into public.contracts (project_id, contract_code, contract_label, service_type_id, payment_type, "
        "fee_value, start_date) values ($1, '01', 'TESTE 050', $2, 'mensal_recorrente', 1000, '2026-01-01') "
        "returning id", p1, svc)

    def em(label):
        return f"{TAG}-{label}@example.invalid"

    async def run_as(uid, q, *args, fetch=False):
        # sem try/finally: num savepoint que falha, o rollback dele já desfaz o papel
        if uid == OWNER:
            return await (c.fetchval(q, *args) if fetch else c.execute(q, *args))
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

    # ---------- (c) checks, dono único e unicidade (como dono) ----------
    TP = ("insert into public.taxpayer_profiles (billing_entity_id, city_ibge_code, state, zip_code) "
          "values ($1, $2::text, $3::text, $4::text)")
    await expect_fail(c, "C1 IBGE com 6 dígitos recusado", do(OWNER, TP, be1, "355030", None, None),
                      "23514", "taxpayer_profiles_city_ibge_code_check")
    await expect_fail(c, "C2 IBGE com letra recusado", do(OWNER, TP, be1, "35503A8", None, None),
                      "23514", "taxpayer_profiles_city_ibge_code_check")
    await expect_fail(c, "C3 UF minúscula recusada", do(OWNER, TP, be1, None, "sp", None),
                      "23514", "taxpayer_profiles_state_check")
    await expect_fail(c, "C4 UF com 3 letras recusada", do(OWNER, TP, be1, None, "SPX", None),
                      "23514", "taxpayer_profiles_state_check")
    await expect_fail(c, "C5 CEP com 7 dígitos recusado", do(OWNER, TP, be1, None, None, "0131010"),
                      "23514", "taxpayer_profiles_zip_code_check")
    await expect_fail(c, "C6 CEP com hífen recusado", do(OWNER, TP, be1, None, None, "01310-100"),
                      "23514", "taxpayer_profiles_zip_code_check")
    await expect_ok(c, "C7 perfil parcial (endereço todo nulo) aceito",
                    do(OWNER, "insert into public.taxpayer_profiles (billing_entity_id) values ($1)", be1))
    await expect_ok(c, "C8 perfil completo aceito", do(
        OWNER, "insert into public.taxpayer_profiles (billing_entity_id, municipal_registration, state_registration, "
               "street, street_number, complement, district, city_name, city_ibge_code, state, zip_code) "
               "values ($1, '123', '456', 'Rua Teste', 'S/N', 'sala 1', 'Centro', 'São Paulo', '3550308', 'SP', "
               "'01310100')", be2))

    CFS1 = ("insert into public.contract_fiscal_settings (contract_id, valid_from, {col}) "
            "values ($1, '2026-09-01', $2::{typ})")
    await expect_fail(c, "C9 local da prestação com 8 dígitos recusado",
                      do(OWNER, CFS1.format(col="service_location_ibge_code", typ="text"), k1, "35503080"),
                      "23514", "contract_fiscal_settings_service_location_ibge_code_check")
    await expect_fail(c, "C10 ISS acima de 100% recusado",
                      do(OWNER, CFS1.format(col="iss_rate_pct", typ="numeric"), k1, "100.01"),
                      "23514", "contract_fiscal_settings_iss_rate_pct_check")
    await expect_fail(c, "C11 ISS negativo recusado",
                      do(OWNER, CFS1.format(col="iss_rate_pct", typ="numeric"), k1, "-1"),
                      "23514", "contract_fiscal_settings_iss_rate_pct_check")
    for col in RETENTIONS:
        await expect_fail(c, f"C12 {col} acima de 100 recusado",
                          do(OWNER, CFS1.format(col=col, typ="numeric"), k1, "101"),
                          "23514", f"contract_fiscal_settings_{col}_check")
    PCT_ALL = ("insert into public.contract_fiscal_settings (contract_id, valid_from, iss_rate_pct, pis_withheld_pct, "
               "cofins_withheld_pct, csll_withheld_pct, irrf_withheld_pct, inss_withheld_pct) "
               "values ($1, ($2::text)::date, $3::numeric, $3::numeric, $3::numeric, $3::numeric, $3::numeric, "
               "$3::numeric)")
    await expect_ok(c, "C13 todos os percentuais em 100 aceitos", do(OWNER, PCT_ALL, k1, "2026-01-01", "100"))
    await expect_ok(c, "C14 todos os percentuais em 0 aceitos", do(OWNER, PCT_ALL, k1, "2026-02-01", "0"))
    await expect_fail(c, "C15 forma de cobrança fora de boleto/pix recusada",
                      do(OWNER, CFS1.format(col="collection_method", typ="text"), k1, "cartao"),
                      "23514", "contract_fiscal_settings_collection_method_check")
    await expect_fail(c, "C16 valid_from fora do dia 1 recusado",
                      do(OWNER, "insert into public.contract_fiscal_settings (contract_id, valid_from) "
                                "values ($1, '2026-01-02')", k1),
                      "23514", "contract_fiscal_settings_valid_from_check")
    await expect_fail(c, "C17 versão repetida (contrato, valid_from) recusada",
                      do(OWNER, "insert into public.contract_fiscal_settings (contract_id, valid_from) "
                                "values ($1, '2026-01-01')", k1),
                      "23505", "contract_fiscal_settings_unique")

    DRE = "insert into public.dre_tax_rates (month, rate) values (($1::text)::date, $2::numeric)"
    for label, rate in (("C18 taxa 0 recusada", "0"), ("C19 taxa 1 recusada", "1"),
                        ("C20 taxa 1,5 recusada", "1.5"), ("C21 taxa negativa recusada", "-0.1")):
        await expect_fail(c, label, do(OWNER, DRE, "2026-08-01", rate), "23514", "dre_tax_rates_rate_check")
    await expect_ok(c, "C22 taxa 0,999999 aceita", do(OWNER, DRE, "2026-08-01", "0.999999"))
    await expect_fail(c, "C23 mês fora do dia 1 recusado", do(OWNER, DRE, "2026-08-15", "0.1"),
                      "23514", "dre_tax_rates_month_check")

    REG = "insert into public.company_tax_regimes (valid_from, regime) values (($1::text)::date, $2::text)"
    await expect_fail(c, "C24 regime com valid_from fora do dia 1 recusado", do(OWNER, REG, "2050-01-02", "simples"),
                      "23514", "company_tax_regimes_valid_from_check")
    await expect_fail(c, "C25 regime fora de simples/lucro_presumido recusado",
                      do(OWNER, REG, "2050-01-01", "lucro_real"), "23514", "company_tax_regimes_regime_check")

    BC = ("insert into public.billing_contacts (billing_entity_id, contract_id, email, role) "
          "values ($1, $2, $3::text, $4::text)")
    for label, email in (("C26 e-mail sem arroba recusado", "sem-arroba.example.invalid"),
                         ("C27 e-mail sem ponto no domínio recusado", "a@b"),
                         ("C28 e-mail com espaço recusado", "a b@example.invalid")):
        await expect_fail(c, label, do(OWNER, BC, be1, None, email, "para"), "23514", "billing_contacts_email_check")
    await expect_fail(c, "C29 papel fora de para/copia recusado", do(OWNER, BC, be1, None, em("c29"), "bcc"),
                      "23514", "billing_contacts_role_check")
    await expect_fail(c, "C30 contato com SPE e contrato ao mesmo tempo recusado",
                      do(OWNER, BC, be1, k1, em("c30"), "para"), "23514", "billing_contacts_one_owner")
    await expect_fail(c, "C31 contato sem dono recusado", do(OWNER, BC, None, None, em("c31"), "para"),
                      "23514", "billing_contacts_one_owner")
    await expect_ok(c, "C32 contato na lista da SPE aceito", do(OWNER, BC, be1, None, em("c32"), "para"))
    await expect_fail(c, "C33 mesmo e-mail (outra caixa) na mesma SPE recusado",
                      do(OWNER, BC, be1, None, em("c32").upper(), "copia"),
                      "23505", "uq_billing_contacts_billing_entity_email")
    await expect_ok(c, "C34 mesmo e-mail na lista do contrato aceito", do(OWNER, BC, None, k1, em("c32"), "copia"))
    await expect_fail(c, "C35 mesmo e-mail repetido na lista do contrato recusado",
                      do(OWNER, BC, None, k1, em("c32"), "para"), "23505", "uq_billing_contacts_contract_email")
    await expect_ok(c, "C36 mesmo e-mail em outra SPE aceito", do(OWNER, BC, be2, None, em("c32"), "para"))

    # ---------- (b) created_by ----------
    CFS_CB = ("insert into public.contract_fiscal_settings (contract_id, valid_from, created_by) "
              "values ($1, ($2::text)::date, $3)")
    CFS_GET = ("select created_by from public.contract_fiscal_settings "
               "where contract_id = $1 and valid_from = ($2::text)::date")
    err = await status_of(c, do(fin, CFS_CB, k1, "2026-03-01", crm))
    got = await c.fetchval(CFS_GET, k1, "2026-03-01")
    record("B1 insert pela API com created_by de outro usuário grava o próprio auth.uid()",
           not str(err).startswith("ERRO") and got == fin, f"{err}; gravou o financeiro: {got == fin}")
    err = await status_of(c, do(fin, "insert into public.contract_fiscal_settings (contract_id, valid_from) "
                                     "values ($1, '2026-04-01')", k1))
    got = await c.fetchval(CFS_GET, k1, "2026-04-01")
    record("B2 insert pela API sem created_by grava auth.uid()",
           not str(err).startswith("ERRO") and got == fin, f"{err}; gravou o financeiro: {got == fin}")
    err = await status_of(c, do(fin, "update public.contract_fiscal_settings set created_by = $2 "
                                     "where contract_id = $1 and valid_from = '2026-03-01'", k1, crm))
    got = await c.fetchval(CFS_GET, k1, "2026-03-01")
    record("B3 update não muda created_by", err == "UPDATE 1" and got == fin, f"{err}; continua o financeiro: {got == fin}")
    err = await status_of(c, do(OWNER, "insert into public.contract_fiscal_settings (contract_id, valid_from) "
                                       "values ($1, '2026-05-01')", k1))
    got = await c.fetchval(CFS_GET, k1, "2026-05-01")
    record("B4 insert sem usuário logado (dono) deixa created_by nulo",
           not str(err).startswith("ERRO") and got is None, str(err))
    err = await status_of(c, do(fin, "insert into public.dre_tax_rates (month, rate, created_by) "
                                     "values ('2026-10-01', 0.15, $1)", crm))
    got = await c.fetchval("select created_by from public.dre_tax_rates where month = '2026-10-01'")
    record("B5 dre_tax_rates: insert pela API grava o próprio auth.uid()",
           not str(err).startswith("ERRO") and got == fin, f"{err}; gravou o financeiro: {got == fin}")
    err = await status_of(c, do(fin, "update public.dre_tax_rates set created_by = $1, rate = 0.16 "
                                     "where month = '2026-10-01'", none_))
    row = await c.fetchrow("select created_by, rate from public.dre_tax_rates where month = '2026-10-01'")
    record("B6 dre_tax_rates: update aplica a taxa e não muda created_by",
           err == "UPDATE 1" and row["created_by"] == fin and row["rate"] == Decimal("0.16"),
           f"{err}; continua o financeiro: {row['created_by'] == fin}; taxa {row['rate']}")
    sp = c.transaction()
    await sp.start()
    err = await status_of(c, do(mst, "insert into public.company_tax_regimes (valid_from, regime, created_by) "
                                     "values ('2046-01-01', 'lucro_presumido', $1)", fin))
    got = await c.fetchval("select created_by from public.company_tax_regimes where valid_from = '2046-01-01'")
    await sp.rollback()
    record("B7 company_tax_regimes: insert do master grava o próprio auth.uid()",
           not str(err).startswith("ERRO") and got == mst, f"{err}; gravou o master: {got == mst}")

    # ---------- (p) permissões por tabela ----------
    cases = {
        "taxpayer_profiles": dict(
            crm_reads=True, fin_writes=True,
            ins="insert into public.taxpayer_profiles (billing_entity_id) values ($1)",
            fin_args=(be3,), crm_args=(be4,),
            upd="update public.taxpayer_profiles set complement = complement"),
        "billing_contacts": dict(
            crm_reads=True, fin_writes=True,
            ins="insert into public.billing_contacts (billing_entity_id, email, role) values ($1, $2::text, 'para')",
            fin_args=(be2, em("p5fin")), crm_args=(be2, em("p5crm")),
            upd="update public.billing_contacts set name = name"),
        "contract_fiscal_settings": dict(
            crm_reads=True, fin_writes=True,
            ins="insert into public.contract_fiscal_settings (contract_id, valid_from) values ($1, ($2::text)::date)",
            fin_args=(k1, "2026-06-01"), crm_args=(k1, "2026-07-01"),
            upd="update public.contract_fiscal_settings set invoice_description = invoice_description"),
        "company_tax_regimes": dict(
            crm_reads=True, fin_writes=False,
            ins="insert into public.company_tax_regimes (valid_from, regime) values (($1::text)::date, 'lucro_presumido')",
            fin_args=("2031-01-01",), crm_args=("2032-01-01",),
            upd="update public.company_tax_regimes set notes = notes"),
        "dre_tax_rates": dict(
            crm_reads=False, fin_writes=True,
            ins="insert into public.dre_tax_rates (month, rate) values (($1::text)::date, 0.2)",
            fin_args=("2026-11-01",), crm_args=("2026-12-01",),
            upd="update public.dre_tax_rates set notes = notes"),
    }
    for t in NEW_TABLES:
        cs = cases[t]
        q_count = f"select count(*) from public.{t}"
        n = await status_of(c, lambda: run_as(fin, q_count, fetch=True))
        record(f"P1 {t}: financeiro lê", isinstance(n, int) and n > 0, f"veio {n}")
        n = await status_of(c, lambda: run_as(crm, q_count, fetch=True))
        if cs["crm_reads"]:
            record(f"P2 {t}: crm lê", isinstance(n, int) and n > 0, f"veio {n}")
        else:
            record(f"P2 {t}: crm não vê nada", n == 0, f"veio {n}")
        n = await status_of(c, lambda: run_as(none_, q_count, fetch=True))
        record(f"P3 {t}: usuário sem módulo não vê nada", n == 0, f"veio {n}")
        await expect_fail(c, f"P4 {t}: anon não lê", lambda: run_as(None, q_count, fetch=True), "42501")
        if cs["fin_writes"]:
            await expect_ok(c, f"P5 {t}: financeiro insere", do(fin, cs["ins"], *cs["fin_args"]))
        else:
            await expect_fail(c, f"P5 {t}: financeiro não insere (só o master)",
                              do(fin, cs["ins"], *cs["fin_args"]), "42501")
        await expect_fail(c, f"P6 {t}: crm não insere", do(crm, cs["ins"], *cs["crm_args"]), "42501")
        st = await status_of(c, do(fin, cs["upd"]))
        if cs["fin_writes"]:
            ok = st.startswith("UPDATE ") and int(st.split()[-1]) > 0
            record(f"P7 {t}: financeiro altera", ok, st)
        else:
            record(f"P7 {t}: financeiro não altera (0 linhas, só o master)", st == "UPDATE 0", st)
        st = await status_of(c, do(crm, cs["upd"]))
        record(f"P8 {t}: crm não altera (0 linhas)", st == "UPDATE 0", st)
        del_sql = f"delete from public.{t}"
        if t in NO_DELETE:
            await expect_fail(c, f"P9 {t}: financeiro não apaga (sem DELETE)", do(fin, del_sql), "42501")
        else:
            st = await status_of(c, do(fin, del_sql))
            record(f"P9 {t}: financeiro não apaga (0 linhas, só o master)", st == "DELETE 0", st)

    # ---------- (r) master sem módulo no regime (savepoint desfeito) ----------
    sp = c.transaction()
    await sp.start()
    n = await status_of(c, lambda: run_as(mst, "select count(*) from public.company_tax_regimes", fetch=True))
    record("R1 master sem módulo lê company_tax_regimes", isinstance(n, int) and n >= 1, f"veio {n}")
    await expect_ok(c, "R2 master insere vigência sem parcela",
                    do(mst, "insert into public.company_tax_regimes (valid_from, regime, notes) "
                            "values ('2045-01-01', 'lucro_presumido', 'R2')", expect="INSERT 0 1"))
    await expect_ok(c, "R3 master altera notes",
                    do(mst, "update public.company_tax_regimes set notes = 'R3' where valid_from = '2045-01-01'",
                       expect="UPDATE 1"))
    await expect_ok(c, "R4 master apaga vigência sem parcela",
                    do(mst, "delete from public.company_tax_regimes where valid_from = '2045-01-01'",
                       expect="DELETE 1"))
    n = await status_of(c, lambda: run_as(mst, "select count(*) from public.dre_tax_rates", fetch=True))
    record("R5 master sem módulo não vê dre_tax_rates (a exceção vale só para o regime)", n == 0, f"veio {n}")
    await sp.rollback()

    # ---------- (g) trava do regime (savepoint desfeito) ----------
    sp = c.transaction()
    await sp.start()
    # vigência de teste [2035-01-01, sem fim), criada pelo dono sem parcela nenhuma nela
    await c.execute("insert into public.company_tax_regimes (valid_from, regime, notes) "
                    "values ('2035-01-01', 'lucro_presumido', 'G')")
    inst_no = itertools.count(1)

    async def inst(status, due, issue=None, received=None):
        await c.execute(
            "insert into public.contract_installments (contract_id, installment_number, revenue_type, due_date, "
            "base_amount, expected_amount, status, issue_date, received_date, received_amount, created_by) "
            "values ($1, $2, 'gerenciamento', ($3::text)::date, 100, 100, $4::text, ($5::text)::date, "
            "($6::text)::date, $7::numeric, $8)",
            k1, next(inst_no), due, status, issue, received, "100" if received else None, fin)

    async def with_inst(name, inst_args, fn, *, fail=True):
        """Cria a parcela num savepoint, roda o caso e desfaz tudo (parcela e efeito)."""
        sp2 = c.transaction()
        await sp2.start()
        try:
            await inst(*inst_args)
        except asyncpg.PostgresError as e:
            record(name, False, f"preparação falhou {e.sqlstate}: {str(e)[:150]}")
            await sp2.rollback()
            return
        if fail:
            await expect_fail(c, name, fn, "55000")
        else:
            await expect_ok(c, name, fn)
        await sp2.rollback()

    DEL_2035 = "delete from public.company_tax_regimes where valid_from = '2035-01-01'"

    await expect_ok(c, "G0a sem parcela: master insere vigência",
                    do(mst, "insert into public.company_tax_regimes (valid_from, regime) values ('2040-01-01', 'simples')",
                       expect="INSERT 0 1"))
    await expect_ok(c, "G0b sem parcela: master muda valid_from",
                    do(mst, "update public.company_tax_regimes set valid_from = '2040-02-01' "
                            "where valid_from = '2040-01-01'", expect="UPDATE 1"))
    await expect_ok(c, "G0c sem parcela: master muda o regime",
                    do(mst, "update public.company_tax_regimes set regime = 'lucro_presumido' "
                            "where valid_from = '2040-02-01'", expect="UPDATE 1"))
    await expect_ok(c, "G0d sem parcela: master apaga",
                    do(mst, "delete from public.company_tax_regimes where valid_from = '2040-02-01'",
                       expect="DELETE 1"))

    EMIT = ("emitida", "2035-03-15", "2035-03-10")
    await with_inst("G1 DELETE da vigência com parcela emitida recusado", EMIT, do(mst, DEL_2035))
    await with_inst("G2 UPDATE de valid_from com parcela emitida na vigência recusado", EMIT,
                    do(mst, "update public.company_tax_regimes set valid_from = '2035-02-01' "
                            "where valid_from = '2035-01-01'"))
    await with_inst("G3 UPDATE do regime com parcela emitida na vigência recusado", EMIT,
                    do(mst, "update public.company_tax_regimes set regime = 'simples' where valid_from = '2035-01-01'"))
    await with_inst("G4 UPDATE só de notes passa mesmo com parcela emitida", EMIT,
                    do(mst, "update public.company_tax_regimes set notes = 'G4' where valid_from = '2035-01-01'",
                       expect="UPDATE 1"), fail=False)
    await with_inst("G5 INSERT de vigência nova sobre parcela emitida recusado", EMIT,
                    do(mst, REG.replace("$1::text", "'2035-02-01'::text").replace("$2::text", "'simples'::text")))
    await with_inst("G6 INSERT de vigência depois da parcela passa", EMIT,
                    do(mst, REG.replace("$1::text", "'2035-06-01'::text").replace("$2::text", "'simples'::text"),
                       expect="INSERT 0 1"), fail=False)
    await with_inst("G7 só issue_date na vigência já trava (DELETE recusado)",
                    ("emitida", "2034-12-15", "2035-02-10"), do(mst, DEL_2035))
    await with_inst("G8 só received_date na vigência já trava (recebida sem nota, DELETE recusado)",
                    ("recebida", "2034-12-15", None, "2035-02-10"), do(mst, DEL_2035))
    await with_inst("G9 só competencia_month na vigência já trava (DELETE recusado)",
                    ("emitida", "2035-01-15", "2034-12-20"), do(mst, DEL_2035))
    await with_inst("G10 parcela cancelada não trava (DELETE passa)",
                    ("cancelada", "2035-03-15", "2035-03-10", "2035-03-20"), do(mst, DEL_2035, expect="DELETE 1"),
                    fail=False)
    await with_inst("G11 parcela projetada não trava (DELETE passa)",
                    ("projetada", "2035-03-15"), do(mst, DEL_2035, expect="DELETE 1"), fail=False)
    await with_inst("G12 sem usuário logado (dono) também é barrado", EMIT, do(OWNER, DEL_2035))
    await with_inst("G13 UPDATE que move valid_from para cima de parcela emitida recusado",
                    ("emitida", "2034-07-15", "2034-07-10"),
                    do(mst, "update public.company_tax_regimes set valid_from = '2034-06-01' "
                            "where valid_from = '2035-01-01'"))
    await with_inst("G14 INSERT antes da primeira vigência sobre parcela emitida recusado",
                    ("emitida", "2024-06-15", "2024-06-10"),
                    do(mst, REG.replace("$1::text", "'2024-01-01'::text").replace("$2::text", "'simples'::text")))
    await sp.rollback()


async def post_check(dsn, before):
    c2 = await asyncpg.connect(dsn, ssl=_lib.ssl_ctx("staging"))
    try:
        async with c2.transaction(readonly=True):
            ro = await c2.fetchval("show transaction_read_only")
            print(f"\nConferência pós-rollback (conexão nova, read_only = {ro})")
            await check(c2, "L1 as 5 tabelas da 050 ausentes",
                        "select count(*) from unnest($1::text[]) t where to_regclass('public.' || t) is not null",
                        0, NEW_TABLES)
            await check(c2, "L2 as 3 funções da 050 ausentes",
                        "select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
                        "and proname = any($1::text[])", 0, NEW_FUNC_NAMES)
            await check(c2, "L3 recursos e permissões da 050 ausentes do catálogo",
                        "select (select count(*) from public.resources where key = any($1::text[])) + "
                        "(select count(*) from public.permissions where resource_key = any($1::text[]))", 0, NEW_TABLES)
            await check(c2, "L4 close_deal igual ao de antes do teste", CLOSE_DEAL_MD5_SQL, before["close_deal"])
            same = []
            for t in EXISTING_TABLES:
                same.append(await c2.fetchval(STRUCT_MD5_SQL, t) == before["struct"][t])
            record("L5 colunas de contracts, billing_entities, clients, proposals e service_types iguais às de antes",
                   all(same), str(dict(zip(EXISTING_TABLES, same))))
            await check(c2, "L6 nenhum usuário de teste",
                        "select count(*) from auth.users where email like '%@example.invalid'", 0)
            await check(c2, "L7 nenhum projeto ou SPE de teste",
                        "select (select count(*) from public.projects where name like 'TESTE 050%') + "
                        "(select count(*) from public.billing_entities where legal_name like 'SPE TESTE 050%')", 0)
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
