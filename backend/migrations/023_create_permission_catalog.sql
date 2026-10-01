-- ============================================================
-- 023_create_permission_catalog.sql
-- Substitui has_module_access('crm')/('financeiro') hardcoded nas
-- policies por um catálogo configurável: modules + resources +
-- permissions + has_permission(). Sem "leitura pública" implícita —
-- se não há permissão cadastrada, não há acesso (decisão do usuário
-- 2026-07-08).
--
-- has_module_access() (019) continua existindo, usada só por
-- profile_modules_write_financeiro -- não migrada agora, fora do
-- escopo desta refatoração.
--
-- ROLLBACK:
--   (recriar as 7 tabelas com as policies has_module_access()
--   originais -- ver migrations 019-022 para o SQL exato de cada uma)
--   drop function if exists has_permission(text, text);
--   drop table if exists permissions;
--   drop table if exists resources;
--   drop table if exists modules;
-- ============================================================

-- 1. Catálogo
create table modules (
  code text primary key,
  label text not null
);

create table resources (
  key text primary key,
  label text not null
);

create table permissions (
  id uuid primary key default gen_random_uuid(),
  module_code text not null references modules(code),
  resource_key text not null references resources(key),
  can_read boolean not null default false,
  can_write boolean not null default false,
  unique (module_code, resource_key)
);

-- 2. Função
create or replace function has_permission(p_resource_key text, p_action text)
returns boolean as $$
  select exists (
    select 1
    from profile_modules pm
    join permissions p on p.module_code = pm.module
    where pm.profile_id = auth.uid()
      and p.resource_key = p_resource_key
      and (
        (p_action = 'read' and p.can_read)
        or (p_action = 'write' and p.can_write)
      )
  );
$$ language sql security definer stable;

-- 3. Seed dos módulos
insert into modules (code, label) values
  ('crm', 'CRM / Vendas'),
  ('financeiro', 'Financeiro'),
  ('engenharia', 'Engenharia'),
  ('reembolso', 'Reembolso');

-- 4. Seed dos recursos (1 por tabela governada)
insert into resources (key, label) values
  ('clients', 'Clientes'),
  ('billing_entities', 'SPE'),
  ('contracts', 'Contratos'),
  ('proposals', 'Propostas'),
  ('proposal_cost_assumptions', 'Premissas de custo da proposta'),
  ('service_types', 'Tipos de serviço'),
  ('teams', 'Times'),
  ('team_members', 'Membros de time');

-- 5. Seed das permissões (matriz já validada nas migrations 021/022
-- + a decisão original de service_types/teams/team_members)
insert into permissions (module_code, resource_key, can_read, can_write) values
  ('crm', 'clients', true, true),
  ('financeiro', 'clients', true, false),
  ('crm', 'billing_entities', true, true),
  ('financeiro', 'billing_entities', true, true),
  ('crm', 'contracts', true, true),
  ('financeiro', 'contracts', true, false),
  ('crm', 'proposals', true, true),
  ('financeiro', 'proposals', true, false),
  ('crm', 'proposal_cost_assumptions', true, true),
  ('financeiro', 'proposal_cost_assumptions', true, false),
  ('crm', 'service_types', true, true),
  ('financeiro', 'service_types', true, true),
  ('financeiro', 'teams', true, true),
  ('financeiro', 'team_members', true, true);

-- 6. Troca as policies das 7 tabelas para usar has_permission()

drop policy if exists clients_write_crm on clients;
drop policy if exists clients_select_crm_financeiro on clients;
create policy clients_write on clients
  for all to authenticated
  using (has_permission('clients', 'write'))
  with check (has_permission('clients', 'write'));
create policy clients_read on clients
  for select to authenticated
  using (has_permission('clients', 'read'));

drop policy if exists billing_entities_write_crm_financeiro on billing_entities;
drop policy if exists billing_entities_select_crm_financeiro on billing_entities;
create policy billing_entities_write on billing_entities
  for all to authenticated
  using (has_permission('billing_entities', 'write'))
  with check (has_permission('billing_entities', 'write'));
create policy billing_entities_read on billing_entities
  for select to authenticated
  using (has_permission('billing_entities', 'read'));

drop policy if exists contracts_write_crm on contracts;
drop policy if exists contracts_select_crm_financeiro on contracts;
create policy contracts_write on contracts
  for all to authenticated
  using (has_permission('contracts', 'write'))
  with check (has_permission('contracts', 'write'));
create policy contracts_read on contracts
  for select to authenticated
  using (has_permission('contracts', 'read'));

drop policy if exists proposals_write_crm on proposals;
drop policy if exists proposals_select_crm_financeiro on proposals;
create policy proposals_write on proposals
  for all to authenticated
  using (has_permission('proposals', 'write'))
  with check (has_permission('proposals', 'write'));
create policy proposals_read on proposals
  for select to authenticated
  using (has_permission('proposals', 'read'));

drop policy if exists proposal_cost_assumptions_write_crm on proposal_cost_assumptions;
drop policy if exists proposal_cost_assumptions_select_crm_financeiro on proposal_cost_assumptions;
create policy proposal_cost_assumptions_write on proposal_cost_assumptions
  for all to authenticated
  using (has_permission('proposal_cost_assumptions', 'write'))
  with check (has_permission('proposal_cost_assumptions', 'write'));
create policy proposal_cost_assumptions_read on proposal_cost_assumptions
  for select to authenticated
  using (has_permission('proposal_cost_assumptions', 'read'));

drop policy if exists service_types_all_authenticated on service_types;
create policy service_types_write on service_types
  for all to authenticated
  using (has_permission('service_types', 'write'))
  with check (has_permission('service_types', 'write'));
create policy service_types_read on service_types
  for select to authenticated
  using (has_permission('service_types', 'read'));

drop policy if exists teams_select_authenticated on teams;
drop policy if exists teams_write_authenticated on teams;
create policy teams_write on teams
  for all to authenticated
  using (has_permission('teams', 'write'))
  with check (has_permission('teams', 'write'));
create policy teams_read on teams
  for select to authenticated
  using (has_permission('teams', 'read'));

drop policy if exists team_members_select_authenticated on team_members;
drop policy if exists team_members_write_authenticated on team_members;
create policy team_members_write on team_members
  for all to authenticated
  using (has_permission('team_members', 'write'))
  with check (has_permission('team_members', 'write'));
create policy team_members_read on team_members
  for select to authenticated
  using (has_permission('team_members', 'read'));
