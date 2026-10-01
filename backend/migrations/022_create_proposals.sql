-- ============================================================
-- 022_create_proposals.sql
-- Funil de vendas: pipeline_stage no projeto + proposals +
-- proposal_cost_assumptions. proposals espelha as mesmas condições
-- comerciais que, quando aceita, são copiadas para contracts.
--
-- ROLLBACK:
--   drop policy if exists proposal_cost_assumptions_select_crm_financeiro on proposal_cost_assumptions;
--   drop policy if exists proposal_cost_assumptions_write_crm on proposal_cost_assumptions;
--   alter table proposal_cost_assumptions disable row level security;
--   drop table if exists proposal_cost_assumptions;
--   drop policy if exists proposals_select_crm_financeiro on proposals;
--   drop policy if exists proposals_write_crm on proposals;
--   alter table proposals disable row level security;
--   drop index if exists idx_proposals_project_version;
--   drop table if exists proposals;
--   alter table projects drop column if exists pipeline_stage;
-- ============================================================

-- 1. pipeline_stage em projects
alter table projects add column pipeline_stage text default 'prospect'
  check (pipeline_stage in ('prospect', 'proposta', 'negociacao', 'fechado_ganho', 'fechado_perdido'));

-- 2. proposals
create table proposals (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id),
  version int not null default 1,
  service_type_id uuid references service_types(id),
  value numeric not null,
  payment_type text not null check (payment_type in ('mensal_recorrente', 'parcela_unica', 'parcelado')),
  installments_count int,
  signed_date date,
  first_due_date date,
  scope_description text,
  status text not null default 'rascunho' check (status in ('rascunho', 'enviada', 'em_negociacao', 'aceita', 'recusada')),
  sent_date date,
  valid_until date,
  lost_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index idx_proposals_project_version on proposals (project_id, version);

-- 3. proposal_cost_assumptions
create table proposal_cost_assumptions (
  id uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references proposals(id) on delete cascade,
  description text not null,
  quantity numeric,
  unit_value numeric,
  total_value numeric not null,
  notes text,
  created_at timestamptz not null default now()
);

-- RLS: proposals -- CRM escreve, CRM + Financeiro leem
alter table proposals enable row level security;
create policy proposals_write_crm on proposals
  for all to authenticated
  using (has_module_access('crm'))
  with check (has_module_access('crm'));
create policy proposals_select_crm_financeiro on proposals
  for select to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'));

-- RLS: proposal_cost_assumptions -- mesmo padrão
alter table proposal_cost_assumptions enable row level security;
create policy proposal_cost_assumptions_write_crm on proposal_cost_assumptions
  for all to authenticated
  using (has_module_access('crm'))
  with check (has_module_access('crm'));
create policy proposal_cost_assumptions_select_crm_financeiro on proposal_cost_assumptions
  for select to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'));
