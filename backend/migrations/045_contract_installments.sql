-- ============================================================
-- 045_contract_installments.sql
-- Calendário de parcelas da receita (contract_installments) e cadastros
-- de apoio. Só estrutura, regras de integridade, permissões e RLS.
--
-- O QUE FAZ:
--   1. public.bank_accounts: contas de destino da receita. Seed:
--      inter_pj (pj, conciliada pela API do banco), pf_diego e pf_murillo
--      (pf). holder_profile_id fica nulo (informativo; quem decide o
--      abatimento é o kind da conta, não o titular).
--   2. public.revenue_types: os 8 tipos de receita da planilha, com as
--      duas regras que as views do DRE (047) vão ler em vez de textos
--      fixos: in_partner_dre (só orcamento = false) e goes_through_split
--      (só reembolso = false). Sem gravação pela API: mudar uma regra muda
--      o DRE, então só por migration.
--   3. public.service_types.default_revenue_type (FK opcional) com o
--      mapeamento SVC-001 Planejamento -> planejamento, SVC-002/SVC-003
--      Monitoramento de Prazo/Custo -> gerenciamento, SVC-004 Auditoria
--      de Qualidade -> auditoria, SVC-005 Outros -> nulo. Aborta se não
--      achar exatamente os 4 serviços pelo par (code, name).
--   4. public.contract_installments: uma linha por parcela.
--      competencia_month = date_trunc('month', due_date::timestamp)::date,
--      coluna gerada. Com due_date puro o Postgres escolhe
--      date_trunc(text, timestamptz), que é STABLE (depende do TimeZone)
--      e não é aceita em coluna gerada; com ::timestamp a cadeia inteira é
--      IMMUTABLE (conferido no catálogo de produção, PG 17.6, 2026-10-05).
--      Sem has_invoice: conta PF significa "sem nota" (item 7).
--   5. public.contract_readjustments: histórico dos reajustes (INCC),
--      um por parcela marcada como ponto de revisão. FK composta garante
--      que a parcela de revisão é do mesmo contrato.
--   6. public.contract_revenue_splits: divisão da receita do contrato.
--      share_kind 'dono' (team_id obrigatório) ou 'a_parte' (team_id
--      opcional; destino provável Diego/Murillo, tratamento a decidir).
--      Gravação SÓ por public.set_contract_splits() (item 9).
--   7. Conta PF => invoice_number nulo, em dois triggers:
--      - na parcela (insert e update de destination_account ou
--        invoice_number). Mudar a parcela de conta NÃO apaga a nota
--        sozinho: quem muda tem que limpar invoice_number na mesma
--        operação, senão dá erro.
--      - em bank_accounts (update de kind): não deixa uma conta virar pf
--        se alguma parcela dela tiver nota.
--   8. Soma 100 por contrato em contract_revenue_splits: constraint
--      trigger DEFERRABLE INITIALLY DEFERRED (confere no commit). Contrato
--      sem nenhuma linha é permitido ("sem split", vira alerta na 047).
--   9. public.set_contract_splits(p_contract_id uuid, p_splits jsonb):
--      troca as linhas do contrato numa transação só (cada requisição da
--      tela é uma transação separada; linha a linha, o trigger adiado
--      barraria a primeira). Valida tudo antes de gravar, trava o
--      contrato (for update), apaga e insere. [] = remover a divisão.
--  10. Catálogo: 5 recursos novos e as permissões. financeiro lê e grava
--      bank_accounts, contract_installments, contract_readjustments e
--      contract_revenue_splits (esta, na prática, só pela função); crm lê
--      contract_installments; financeiro e crm leem revenue_types.
--  11. RLS em todas as tabelas novas, no padrão has_permission() da 023.
--      Sem is_master(). Privilégios: anon sem nada; authenticated sem
--      TRUNCATE/REFERENCES/TRIGGER (TRUNCATE não passa pela RLS); em
--      revenue_types e contract_revenue_splits, authenticated só tem
--      SELECT.
--
-- NÃO FAZ (fica para as próximas):
--   046: contracts.first_due_date; close_deal copiando first_due_date;
--        FK/check/índice em bank_transactions.matched_contract_installment_id;
--        funções de geração (mensal e parcela única), extensão do
--        horizonte de 12 meses, aplicação do reajuste e confirmação de
--        recebimento (conciliação automática e manual).
--   047: views do DRE (security_invoker, portão has_permission('dre',
--        'read'), recurso 'dre').
--
-- ROLLBACK (na ordem; apaga as parcelas, splits e reajustes gravados):
--   drop function if exists public.set_contract_splits(uuid, jsonb);
--   drop table if exists public.contract_readjustments;
--   drop table if exists public.contract_revenue_splits;   -- constraint trigger cai junto
--   drop table if exists public.contract_installments;     -- triggers caem junto
--   drop trigger if exists trg_bank_accounts_kind_guard on public.bank_accounts;
--   drop function if exists public.fn_contract_revenue_splits_sum_100();
--   drop function if exists public.fn_contract_installments_pf_no_invoice();
--   drop function if exists public.fn_bank_accounts_kind_guard();
--   alter table public.service_types drop column if exists default_revenue_type;
--   drop table if exists public.revenue_types;
--   drop table if exists public.bank_accounts;
--   delete from public.permissions where resource_key in
--     ('bank_accounts', 'revenue_types', 'contract_installments',
--      'contract_readjustments', 'contract_revenue_splits');
--   delete from public.resources where key in
--     ('bank_accounts', 'revenue_types', 'contract_installments',
--      'contract_readjustments', 'contract_revenue_splits');
--   -- NÃO dropar public.set_updated_at(): compartilhada (033/037).
-- ============================================================

-- 1. bank_accounts
create table public.bank_accounts (
  code text primary key,
  label text not null,
  kind text not null check (kind in ('pj', 'pf')),
  holder_profile_id uuid references public.profiles(id),
  reconciled_via_bank_api boolean not null default false,
  created_at timestamptz not null default now(),
  constraint bank_accounts_api_only_pj check (not reconciled_via_bank_api or kind = 'pj')
);

insert into public.bank_accounts (code, label, kind, holder_profile_id, reconciled_via_bank_api) values
  ('inter_pj',   'Inter PJ',   'pj', null, true),
  ('pf_diego',   'PF Diego',   'pf', null, false),
  ('pf_murillo', 'PF Murillo', 'pf', null, false);

-- 2. revenue_types
create table public.revenue_types (
  code text primary key,
  label text not null,
  in_partner_dre boolean not null,
  goes_through_split boolean not null,
  created_at timestamptz not null default now()
);

insert into public.revenue_types (code, label, in_partner_dre, goes_through_split) values
  ('gerenciamento',      'Gerenciamento',      true,  true),
  ('relatorio_fundo',    'Relatório Fundo',    true,  true),
  ('reembolso',          'Reembolso',          true,  false),
  ('orcamento',          'Orçamento',          false, true),
  ('auditoria',          'Auditoria',          true,  true),
  ('planejamento',       'Planejamento',       true,  true),
  ('documentacao_final', 'Documentação Final', true,  true),
  ('fre',                'FRE',                true,  true);

-- 3. service_types.default_revenue_type
alter table public.service_types
  add column default_revenue_type text references public.revenue_types(code);

do $$
declare
  v_rows integer;
  v_total integer := 0;
begin
  update public.service_types set default_revenue_type = 'planejamento'
  where code = 'SVC-001' and name = 'Planejamento';
  get diagnostics v_rows = row_count; v_total := v_total + v_rows;

  update public.service_types set default_revenue_type = 'gerenciamento'
  where (code, name) in (('SVC-002', 'Monitoramento de Prazo'), ('SVC-003', 'Monitoramento de Custo'));
  get diagnostics v_rows = row_count; v_total := v_total + v_rows;

  update public.service_types set default_revenue_type = 'auditoria'
  where code = 'SVC-004' and name = 'Auditoria de Qualidade';
  get diagnostics v_rows = row_count; v_total := v_total + v_rows;

  if v_total <> 4 then
    raise exception 'service_types: esperava mapear 4 serviços pelo par (code, name), mapeou %', v_total;
  end if;
end;
$$;

-- 4. contract_installments
create table public.contract_installments (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts(id),
  installment_number integer not null check (installment_number > 0),
  revenue_type text not null references public.revenue_types(code),
  origin text not null default 'projetada' check (origin in ('projetada', 'avulsa')),
  due_date date not null,
  competencia_month date generated always as (date_trunc('month', due_date::timestamp)::date) stored,
  issue_date date,
  received_date date,
  base_amount numeric(14,2) not null check (base_amount >= 0),
  readjustment_factor numeric(12,8) not null default 1 check (readjustment_factor > 0),
  expected_amount numeric(14,2) not null check (expected_amount >= 0),
  invoiced_amount numeric(14,2) check (invoiced_amount >= 0),
  received_amount numeric(14,2) check (received_amount >= 0),
  status text not null default 'projetada'
    check (status in ('projetada', 'emitida', 'recebida', 'cancelada')),
  is_revision_point boolean not null default false,
  destination_account text not null default 'inter_pj' references public.bank_accounts(code),
  invoice_number text check (invoice_number is null or btrim(invoice_number) <> ''),
  notes text,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (contract_id, installment_number),
  -- alvo da FK composta de contract_readjustments
  constraint contract_installments_contract_id_id_key unique (contract_id, id),
  constraint contract_installments_recebida_check
    check (status <> 'recebida' or (received_date is not null and received_amount is not null)),
  constraint contract_installments_emitida_check
    check (status <> 'emitida' or issue_date is not null)
);

create index idx_contract_installments_competencia on public.contract_installments (competencia_month);
create index idx_contract_installments_destination on public.contract_installments (destination_account);

create trigger contract_installments_set_updated_at
  before update on public.contract_installments
  for each row execute function public.set_updated_at();

-- 5. contract_readjustments
create table public.contract_readjustments (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts(id),
  revision_installment_id uuid not null,
  index_code text not null default 'INCC',
  reference_month date not null check (extract(day from reference_month) = 1),
  percentage numeric(8,4) not null,
  factor_before numeric(12,8) not null check (factor_before > 0),
  factor_after numeric(12,8) not null check (factor_after > 0),
  applied_by uuid not null references public.profiles(id),
  applied_at timestamptz not null default now(),
  notes text,
  unique (revision_installment_id),
  constraint contract_readjustments_installment_same_contract
    foreign key (contract_id, revision_installment_id)
    references public.contract_installments (contract_id, id)
);

-- 6. contract_revenue_splits
create table public.contract_revenue_splits (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts(id),
  share_kind text not null check (share_kind in ('dono', 'a_parte')),
  team_id uuid references public.teams(id),
  scope text not null check (btrim(scope) <> ''),
  percentage numeric(5,2) not null check (percentage > 0 and percentage <= 100),
  created_at timestamptz not null default now(),
  constraint contract_revenue_splits_dono_has_team check (share_kind <> 'dono' or team_id is not null),
  constraint contract_revenue_splits_unique unique nulls not distinct (contract_id, share_kind, team_id, scope)
);

-- 7. Conta PF => sem nota
-- security definer nos dois: a checagem precisa enxergar bank_accounts e
-- contract_installments inteiras, sem depender da RLS de quem disparou
-- (uma linha escondida pela RLS faria o exists dar false e furar a regra).
-- Revoke de EXECUTE nas funções de trigger como na 043.
create function public.fn_contract_installments_pf_no_invoice()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.invoice_number is not null and exists (
    select 1 from public.bank_accounts
    where code = new.destination_account and kind = 'pf'
  ) then
    raise exception 'parcela em conta PF não pode ter nota fiscal (conta %): limpe invoice_number na mesma operação',
      new.destination_account
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke execute on function public.fn_contract_installments_pf_no_invoice() from public, anon, authenticated;

create trigger trg_contract_installments_pf_no_invoice
  before insert or update of destination_account, invoice_number on public.contract_installments
  for each row
  execute function public.fn_contract_installments_pf_no_invoice();

create function public.fn_bank_accounts_kind_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.kind = 'pf' and old.kind is distinct from 'pf' and exists (
    select 1 from public.contract_installments
    where destination_account = new.code and invoice_number is not null
  ) then
    raise exception 'conta % tem parcelas com nota fiscal e não pode virar PF', new.code
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke execute on function public.fn_bank_accounts_kind_guard() from public, anon, authenticated;

create trigger trg_bank_accounts_kind_guard
  before update of kind on public.bank_accounts
  for each row
  execute function public.fn_bank_accounts_kind_guard();

-- 8. Soma 100 por contrato (adiado para o commit)
-- security definer: no commit o trigger roda como quem abriu a transação
-- (não como o dono de set_contract_splits) e a soma precisa ver todas as
-- linhas do contrato, sem depender da RLS.
create function public.fn_contract_revenue_splits_sum_100()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_ids uuid[] := '{}';
  v_contract uuid;
  v_count integer;
  v_sum numeric;
begin
  if tg_op in ('INSERT', 'UPDATE') then
    v_ids := v_ids || new.contract_id;
  end if;
  if tg_op in ('UPDATE', 'DELETE') then
    v_ids := v_ids || old.contract_id;
  end if;

  foreach v_contract in array v_ids loop
    select count(*), coalesce(sum(percentage), 0)
      into v_count, v_sum
      from public.contract_revenue_splits
      where contract_id = v_contract;

    if v_count > 0 and v_sum <> 100 then
      raise exception 'divisão de receita do contrato % soma % (deve somar 100)', v_contract, v_sum
        using errcode = '23514';
    end if;
  end loop;

  return null;
end;
$$;

revoke execute on function public.fn_contract_revenue_splits_sum_100() from public, anon, authenticated;

create constraint trigger trg_contract_revenue_splits_sum_100
  after insert or update or delete on public.contract_revenue_splits
  deferrable initially deferred
  for each row
  execute function public.fn_contract_revenue_splits_sum_100();

-- 9. set_contract_splits (única porta de escrita dos splits)
-- p_splits: lista JSON de objetos
--   {"share_kind": "dono"|"a_parte", "team_id": "<uuid>"|null,
--    "scope": "<texto>", "percentage": <número com até 2 casas>}
-- Devolve quantas linhas ficaram gravadas.
create function public.set_contract_splits(p_contract_id uuid, p_splits jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_item jsonb;
  v_idx integer := 0;
  v_kind text;
  v_team uuid;
  v_scope text;
  v_pct numeric;
  v_sum numeric := 0;
  v_rows integer;
begin
  if not public.has_permission('contract_revenue_splits', 'write') then
    raise exception 'Sem permissão para alterar a divisão de receita do contrato'
      using errcode = '42501';
  end if;

  if p_contract_id is null then
    raise exception 'p_contract_id é obrigatório' using errcode = '22004';
  end if;

  if p_splits is null or jsonb_typeof(p_splits) <> 'array' then
    raise exception 'p_splits deve ser uma lista JSON (use [] para remover a divisão)'
      using errcode = '22023';
  end if;

  perform 1 from public.contracts where id = p_contract_id for update;
  if not found then
    raise exception 'contrato % não encontrado', p_contract_id using errcode = 'P0002';
  end if;

  for v_item in select value from jsonb_array_elements(p_splits) loop
    v_idx := v_idx + 1;

    if jsonb_typeof(v_item) <> 'object' then
      raise exception 'item %: deve ser um objeto JSON', v_idx using errcode = '22023';
    end if;

    v_kind := v_item ->> 'share_kind';
    if v_kind is null or v_kind not in ('dono', 'a_parte') then
      raise exception 'item %: share_kind deve ser dono ou a_parte', v_idx using errcode = '22023';
    end if;

    v_scope := btrim(coalesce(v_item ->> 'scope', ''));
    if v_scope = '' then
      raise exception 'item %: scope é obrigatório', v_idx using errcode = '22023';
    end if;

    begin
      v_team := nullif(v_item ->> 'team_id', '')::uuid;
      v_pct := (v_item ->> 'percentage')::numeric;
    exception when invalid_text_representation then
      raise exception 'item %: team_id ou percentage em formato inválido', v_idx using errcode = '22023';
    end;

    if v_kind = 'dono' and v_team is null then
      raise exception 'item %: team_id é obrigatório na fatia do dono', v_idx using errcode = '22023';
    end if;

    if v_team is not null and not exists (select 1 from public.teams where id = v_team) then
      raise exception 'item %: time % não existe', v_idx, v_team using errcode = '23503';
    end if;

    if v_pct is null or v_pct <= 0 or v_pct > 100 or v_pct <> round(v_pct, 2) then
      raise exception 'item %: percentage deve ser maior que 0, no máximo 100 e com até 2 casas', v_idx
        using errcode = '22023';
    end if;

    v_sum := v_sum + v_pct;
  end loop;

  if v_idx > 0 and v_sum <> 100 then
    raise exception 'a soma dos percentuais deve ser 100 (veio %)', v_sum using errcode = '23514';
  end if;

  delete from public.contract_revenue_splits where contract_id = p_contract_id;

  insert into public.contract_revenue_splits (contract_id, share_kind, team_id, scope, percentage)
  select p_contract_id,
         e.x ->> 'share_kind',
         nullif(e.x ->> 'team_id', '')::uuid,
         btrim(e.x ->> 'scope'),
         (e.x ->> 'percentage')::numeric
  from jsonb_array_elements(p_splits) as e(x);

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke execute on function public.set_contract_splits(uuid, jsonb) from public, anon;
grant execute on function public.set_contract_splits(uuid, jsonb) to authenticated;

-- 10. Catálogo de permissões
insert into public.resources (key, label) values
  ('bank_accounts', 'Contas bancárias'),
  ('revenue_types', 'Tipos de receita'),
  ('contract_installments', 'Parcelas de contrato'),
  ('contract_readjustments', 'Reajustes de contrato'),
  ('contract_revenue_splits', 'Divisão de receita do contrato');

insert into public.permissions (module_code, resource_key, can_read, can_write) values
  ('financeiro', 'bank_accounts', true, true),
  ('financeiro', 'revenue_types', true, false),
  ('crm', 'revenue_types', true, false),
  ('financeiro', 'contract_installments', true, true),
  ('crm', 'contract_installments', true, false),
  ('financeiro', 'contract_readjustments', true, true),
  ('financeiro', 'contract_revenue_splits', true, true);

-- 11. RLS e privilégios
alter table public.bank_accounts enable row level security;
alter table public.revenue_types enable row level security;
alter table public.contract_installments enable row level security;
alter table public.contract_readjustments enable row level security;
alter table public.contract_revenue_splits enable row level security;

create policy bank_accounts_read on public.bank_accounts
  for select to authenticated
  using (public.has_permission('bank_accounts', 'read'));
create policy bank_accounts_write on public.bank_accounts
  for all to authenticated
  using (public.has_permission('bank_accounts', 'write'))
  with check (public.has_permission('bank_accounts', 'write'));

-- revenue_types: só leitura pela API (sem policy de escrita e sem grant)
create policy revenue_types_read on public.revenue_types
  for select to authenticated
  using (public.has_permission('revenue_types', 'read'));

create policy contract_installments_read on public.contract_installments
  for select to authenticated
  using (public.has_permission('contract_installments', 'read'));
create policy contract_installments_write on public.contract_installments
  for all to authenticated
  using (public.has_permission('contract_installments', 'write'))
  with check (public.has_permission('contract_installments', 'write'));

create policy contract_readjustments_read on public.contract_readjustments
  for select to authenticated
  using (public.has_permission('contract_readjustments', 'read'));
create policy contract_readjustments_write on public.contract_readjustments
  for all to authenticated
  using (public.has_permission('contract_readjustments', 'write'))
  with check (public.has_permission('contract_readjustments', 'write'));

-- contract_revenue_splits: só leitura pela API; escrita só por
-- set_contract_splits() (security definer, não depende de policy nem grant)
create policy contract_revenue_splits_read on public.contract_revenue_splits
  for select to authenticated
  using (public.has_permission('contract_revenue_splits', 'read'));

-- Privilégios explícitos (não depende dos default privileges do projeto)
revoke all on table
  public.bank_accounts,
  public.revenue_types,
  public.contract_installments,
  public.contract_readjustments,
  public.contract_revenue_splits
from public, anon, authenticated;

grant select, insert, update, delete on table
  public.bank_accounts,
  public.contract_installments,
  public.contract_readjustments
to authenticated;

grant select on table
  public.revenue_types,
  public.contract_revenue_splits
to authenticated;
