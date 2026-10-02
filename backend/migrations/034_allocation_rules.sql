-- ============================================================
-- 034_allocation_rules.sql
-- Fase A do módulo Financeiro: generaliza o rateio fixo de hoje
-- (team_cost_allocations, migration 030) para REGRAS NOMEADAS e
-- EDITÁVEIS (allocation_rules + allocation_rule_splits).
--
-- Migration ADITIVA: renomeia cost_centers -> expense_categories
-- (rename preserva a FK reimbursement_items.cost_center_id, pois é
-- rename de tabela, não drop/create), cria o catálogo de regras,
-- semeia as 3 regras equivalentes às de team_cost_allocations, e
-- adiciona reimbursement_items.allocation_rule_id (nullable por ora).
--
-- NÃO remove team_cost_allocations — a desativação vem numa migration
-- separada, depois que o código do Reembolso passar a gravar
-- allocation_rule_id na criação do item.
--
-- A escrita das regras reaproveita has_permission('allocation_rules',
-- 'write'); a linha de resource/permission 'allocation_rules' é criada
-- aqui mesmo (módulo financeiro).
--
-- ROLLBACK:
--   alter table reimbursement_items drop column if exists allocation_rule_id;
--   delete from permissions where module_code = 'financeiro' and resource_key = 'allocation_rules';
--   delete from resources where key = 'allocation_rules';
--   drop table if exists allocation_rule_splits;
--   drop table if exists allocation_rules;
--   alter table expense_categories rename to cost_centers;
-- ============================================================

-- 1. Renomeia cost_centers -> expense_categories (preserva a FK de
--    reimbursement_items.cost_center_id automaticamente).
alter table cost_centers rename to expense_categories;

-- 2. Catálogo de regras de rateio (nomeadas e editáveis).
create table allocation_rules (
  id uuid primary key default gen_random_uuid(),
  name text not null unique
);

create table allocation_rule_splits (
  id uuid primary key default gen_random_uuid(),
  rule_id uuid not null references allocation_rules(id) on delete cascade,
  team_id uuid not null references teams(id),
  percentage numeric not null check (percentage > 0 and percentage <= 100),
  unique (rule_id, team_id)
);

-- 3. Semeia as 3 regras que já existem hoje (mesma lógica de
--    team_cost_allocations, agora nomeada e editável). Busca os times
--    pelo NOME, não por UUID fixo (consistente entre ambientes).
insert into allocation_rules (name) values
  ('Time Carlos 100%'), ('Time Weslley 100%'), ('Rateio Sócios 50/50 (Carlos/Weslley)');

insert into allocation_rule_splits (rule_id, team_id, percentage)
select r.id, t.id, 100 from allocation_rules r, teams t
where r.name = 'Time Carlos 100%' and t.name = 'Carlos'
union all
select r.id, t.id, 100 from allocation_rules r, teams t
where r.name = 'Time Weslley 100%' and t.name = 'Weslley'
union all
select r.id, t.id, 50 from allocation_rules r, teams t
where r.name = 'Rateio Sócios 50/50 (Carlos/Weslley)' and t.name = 'Carlos'
union all
select r.id, t.id, 50 from allocation_rules r, teams t
where r.name = 'Rateio Sócios 50/50 (Carlos/Weslley)' and t.name = 'Weslley';

-- 4. Coluna em reimbursement_items (nullable — itens antigos não tinham
--    isso registrado explicitamente, só inferido na consulta).
alter table reimbursement_items add column allocation_rule_id uuid references allocation_rules(id);

-- 5. RLS: leitura ampla (qualquer autenticado lê o que está vigente),
--    escrita só financeiro via has_permission('allocation_rules', 'write').
alter table allocation_rules enable row level security;
create policy allocation_rules_read on allocation_rules for select to authenticated using (true);
create policy allocation_rules_write on allocation_rules for all to authenticated
  using (has_permission('allocation_rules', 'write'))
  with check (has_permission('allocation_rules', 'write'));

alter table allocation_rule_splits enable row level security;
create policy allocation_rule_splits_read on allocation_rule_splits for select to authenticated using (true);
create policy allocation_rule_splits_write on allocation_rule_splits for all to authenticated
  using (has_permission('allocation_rules', 'write'))
  with check (has_permission('allocation_rules', 'write'));

-- 6. Recurso/permissão pro módulo financeiro.
insert into resources (key, label) values ('allocation_rules', 'Regras de rateio')
  on conflict (key) do nothing;
insert into permissions (module_code, resource_key, can_read, can_write)
values ('financeiro', 'allocation_rules', true, true);
