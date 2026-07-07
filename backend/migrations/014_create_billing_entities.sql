-- ============================================================
-- 014_create_billing_entities.sql (SPE)
-- ROLLBACK: drop table billing_entities;
-- ============================================================
create table billing_entities (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references projects(id),
  legal_name text not null,
  cnpj text not null unique,
  address text,
  bank_name text,
  bank_agency text,
  bank_account text,
  created_at timestamptz not null default now()
);
