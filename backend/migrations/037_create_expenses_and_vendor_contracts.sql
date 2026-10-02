-- ============================================================
-- 037_create_expenses_and_vendor_contracts.sql
-- Núcleo de Contas a Pagar (módulo Financeiro, Fase B core):
--   1. expenses            — despesas gerais (com updated_at via trigger)
--   2. vendor_contracts    — contratos de tomada de serviço (fornecedor
--                            recorrente, incluindo PJ) + aditivos +
--                            detalhe de contrato de pessoal PJ
--   3. RLS restrita ao módulo financeiro (não é "qualquer autenticado"
--      como o Reembolso — é dado financeiro da empresa)
--   4. catálogo de permissões (resources + permissions)
--
-- ADITIVA: só cria tabelas/trigger/policies/catálogo novos.
--
-- set_updated_at() já existe desde a migration 033 (confirmado no schema
-- real: mesma assinatura `() returns trigger`, mesmo corpo com
-- clock_timestamp()). O `create or replace` abaixo é idempotente e NÃO
-- altera o trigger existente de reimbursement_reports. A função é
-- COMPARTILHADA — o rollback desta migration NÃO deve dropá-la.
--
-- ROLLBACK:
--   delete from permissions where module_code='financeiro' and resource_key in ('expenses','vendor_contracts');
--   delete from resources where key in ('expenses','vendor_contracts');
--   drop table if exists personnel_contract_details;
--   drop table if exists vendor_contract_amendments;
--   drop table if exists vendor_contracts;
--   drop table if exists expenses;  -- (trigger expenses_set_updated_at cai junto)
--   -- NÃO dropar set_updated_at(): compartilhada com reimbursement_reports (033).
-- ============================================================

-- 1. Despesas gerais
create table expenses (
  id uuid primary key default gen_random_uuid(),
  category_id uuid not null references expense_categories(id),
  project_id uuid references projects(id),
  allocation_rule_id uuid references allocation_rules(id),
  vendor_name text not null,
  document_number text,
  competencia_month date not null,
  due_date date,
  payment_date date,
  value numeric not null,
  status text not null default 'pendente' check (status in ('pendente', 'pago', 'atrasado')),
  paid_via_account text,
  created_by uuid not null references profiles(id),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;
-- (reaproveita a função já existente desde 033 — create or replace é
-- idempotente, não quebra se já existir igual)

create trigger expenses_set_updated_at
  before update on expenses
  for each row execute function set_updated_at();

-- 2. Contratos de tomada de serviço (fornecedor recorrente, incluindo PJ)
create table vendor_contracts (
  id uuid primary key default gen_random_uuid(),
  vendor_name text not null,
  cnpj text,
  contract_type text not null check (contract_type in ('aluguel', 'contabilidade', 'pessoal_pj', 'outros')),
  category_id uuid not null references expense_categories(id),
  monthly_value numeric not null,
  withholding_percentage numeric,
  start_date date not null,
  end_date date,
  status text not null default 'ativo' check (status in ('ativo', 'encerrado')),
  created_at timestamptz not null default now()
);

create table vendor_contract_amendments (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references vendor_contracts(id) on delete cascade,
  amendment_number int not null,
  new_value numeric not null,
  effective_start_date date not null,
  notes text,
  created_at timestamptz not null default now(),
  unique (contract_id, amendment_number)
);

create table personnel_contract_details (
  contract_id uuid primary key references vendor_contracts(id) on delete cascade,
  profile_id uuid not null references profiles(id)
);

-- 3. RLS: restrito ao módulo financeiro (não é "qualquer autenticado"
-- como Reembolso — é dado financeiro da empresa, só quem tem o módulo
-- financeiro lança/vê)

alter table expenses enable row level security;
create policy expenses_all on expenses for all to authenticated
  using (has_permission('expenses', 'write'))
  with check (has_permission('expenses', 'write'));

alter table vendor_contracts enable row level security;
create policy vendor_contracts_all on vendor_contracts for all to authenticated
  using (has_permission('vendor_contracts', 'write'))
  with check (has_permission('vendor_contracts', 'write'));

alter table vendor_contract_amendments enable row level security;
create policy vendor_contract_amendments_all on vendor_contract_amendments for all to authenticated
  using (has_permission('vendor_contracts', 'write'))
  with check (has_permission('vendor_contracts', 'write'));

alter table personnel_contract_details enable row level security;
create policy personnel_contract_details_all on personnel_contract_details for all to authenticated
  using (has_permission('vendor_contracts', 'write'))
  with check (has_permission('vendor_contracts', 'write'));

-- 4. Catálogo de permissões
insert into resources (key, label) values
  ('expenses', 'Despesas gerais'),
  ('vendor_contracts', 'Contratos de fornecedor')
on conflict (key) do nothing;

insert into permissions (module_code, resource_key, can_read, can_write)
values
  ('financeiro', 'expenses', true, true),
  ('financeiro', 'vendor_contracts', true, true);
