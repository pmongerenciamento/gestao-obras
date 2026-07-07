-- ============================================================
-- 012_create_service_types.sql
-- ROLLBACK: drop table service_types;
-- ============================================================
create table service_types (
  id uuid primary key default gen_random_uuid(),
  code varchar(10) not null unique,
  name text not null,
  description text,
  requires_manual_description boolean not null default false
);

insert into service_types (code, name, requires_manual_description) values
  ('SVC-001', 'Planejamento', false),
  ('SVC-002', 'Monitoramento de Prazo', false),
  ('SVC-003', 'Monitoramento de Custo', false),
  ('SVC-004', 'Auditoria de Qualidade', false),
  ('SVC-005', 'Outros', true);
