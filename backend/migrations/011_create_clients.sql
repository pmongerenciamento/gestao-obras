-- ============================================================
-- 011_create_clients.sql
-- ROLLBACK: drop table clients;
-- ============================================================
create table clients (
  id uuid primary key default gen_random_uuid(),
  code varchar(3) not null unique,
  legal_name text not null,
  trade_name text,
  cnpj text,
  contact_name text,
  contact_email text,
  contact_phone text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_clients_code on clients(code);
