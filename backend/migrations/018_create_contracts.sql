-- ============================================================
-- 018_create_contracts.sql
-- Contratos por projeto (código de 2 dígitos, tipo de serviço, forma de
-- pagamento/honorário, reajuste, vigência) — Fase 1 aditiva do CRM.
--
-- RLS: mesmo fallback "to authenticated" com TODO, seguindo o padrão das
-- migrations 016/017 (sem policy de module_access ainda, isso vem na
-- próxima migration).
--
-- ROLLBACK:
--   drop policy if exists contracts_all_authenticated on contracts;
--   alter table contracts disable row level security;
--   drop table if exists contracts;
-- ============================================================

create table contracts (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id),
  contract_code varchar(2) not null,
  contract_label text not null,
  service_type_id uuid references service_types(id),
  payment_type text not null check (payment_type in ('mensal_recorrente', 'parcela_unica', 'parcelado')),
  fee_value numeric not null,
  installments_count int,
  readjustment_index text default 'INCC',
  readjustment_cycle_months int default 12,
  document_lead_days int,
  start_date date not null,
  end_date date,
  status text not null default 'ativo' check (status in ('ativo', 'suspenso', 'encerrado')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index idx_contracts_project_code on contracts (project_id, contract_code);

-- RLS: mesmo fallback "to authenticated" com TODO, seguindo o padrão das
-- migrations 016/017 (sem policy de module_access ainda, isso vem na
-- próxima migration).
alter table contracts enable row level security;
create policy contracts_all_authenticated on contracts
  for all to authenticated using (true) with check (true);
-- TODO: trocar por has_module_access('crm') quando profile_modules existir.
