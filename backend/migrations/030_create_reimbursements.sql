-- ============================================================
-- 030_create_reimbursements.sql
-- Módulo de Reembolso: aberto a qualquer funcionário autenticado
-- (não passa pelo sistema de módulos como o resto do CRM/Financeiro)
-- — cada um só lê/escreve os próprios relatórios em rascunho;
-- aprovação restrita ao módulo financeiro via has_permission().
--
-- 1. cost_centers: compartilhado com o futuro módulo Financeiro, não
--    é exclusivo do Reembolso.
-- 2. team_cost_allocations: regra de rateio por time de origem (quem
--    fez a despesa determina o destino), resolvida pelo NOME do time
--    (não UUID fixo) para não depender de IDs hardcoded entre ambientes.
-- 3. reimbursement_reports / reimbursement_items: relatório e itens.
-- 4. reimbursement_rate_rules: taxas vigentes (km, alimentação).
--
-- ROLLBACK:
--   revoke execute on function has_permission(text, text) from authenticated; -- (não recriar, já existe desde 023 — não mexer)
--   delete from permissions where module_code = 'financeiro' and resource_key = 'reimbursement_reports';
--   delete from resources where key = 'reimbursement_reports';
--   drop table if exists reimbursement_items;
--   drop table if exists reimbursement_reports;
--   drop table if exists reimbursement_rate_rules;
--   drop table if exists team_cost_allocations;
--   drop table if exists cost_centers;
-- ============================================================

-- 1. Centros de custo (compartilhado com o futuro módulo Financeiro —
-- não é exclusivo do Reembolso)
create table cost_centers (
  id uuid primary key default gen_random_uuid(),
  name text not null unique
);

insert into cost_centers (name) values
  ('Deslocamento Escritório'),
  ('TI e Equipamentos'),
  ('Consumo/Manutenção Escritório'),
  ('Comercial (brindes, refeições, eventos)'),
  ('Outros');

-- 2. Regra de rateio por time de origem (quem fez a despesa determina
-- o destino) — busca os times pelo NOME, não por UUID fixo:
create table team_cost_allocations (
  id uuid primary key default gen_random_uuid(),
  requester_team_id uuid not null references teams(id),
  target_team_id uuid not null references teams(id),
  percentage numeric not null check (percentage > 0 and percentage <= 100),
  unique (requester_team_id, target_team_id)
);

insert into team_cost_allocations (requester_team_id, target_team_id, percentage)
select t.id, t.id, 100 from teams t where t.name = 'Carlos'
union all
select t.id, t.id, 100 from teams t where t.name = 'Weslley'
union all
select dm.id, c.id, 50 from teams dm, teams c where dm.name = 'Diego/Murillo' and c.name = 'Carlos'
union all
select dm.id, w.id, 50 from teams dm, teams w where dm.name = 'Diego/Murillo' and w.name = 'Weslley';

-- 3. Relatórios e itens de reembolso
create table reimbursement_reports (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references profiles(id),
  period_start date not null,
  period_end date not null,
  status text not null default 'rascunho'
    check (status in ('rascunho', 'enviado', 'aprovado', 'rejeitado')),
  approved_by uuid references profiles(id),
  approved_at timestamptz,
  rejection_reason text,
  created_at timestamptz not null default now()
);

create table reimbursement_items (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reimbursement_reports(id) on delete cascade,
  type text not null check (type in (
    'deslocamento_escritorio', 'visita_cliente', 'visita_comercial',
    'alimentacao', 'outros'
  )),
  project_id uuid references projects(id),
  cost_center_id uuid references cost_centers(id),
  expense_date date not null,
  description varchar(280) not null,
  km_traveled numeric,
  km_rate numeric,
  toll_amount numeric not null default 0,
  other_amount numeric not null default 0,
  requires_preapproval boolean not null default false,
  total_amount numeric not null,
  created_at timestamptz not null default now(),
  check (
    (type in ('visita_cliente', 'visita_comercial') and project_id is not null)
    or (type not in ('visita_cliente', 'visita_comercial') and cost_center_id is not null)
  )
);

-- 4. Taxas vigentes
create table reimbursement_rate_rules (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in (
    'deslocamento_escritorio', 'visita_cliente', 'alimentacao'
  )),
  value numeric not null,
  unit text not null check (unit in ('por_km', 'valor_fixo_diario')),
  auto_readjust boolean not null default false,
  effective_start_date date not null,
  effective_end_date date,
  notes text,
  created_at timestamptz not null default now()
);

insert into reimbursement_rate_rules (type, value, unit, effective_start_date) values
  ('deslocamento_escritorio', 0.50, 'por_km', current_date),
  ('visita_cliente', 0.90, 'por_km', current_date),
  ('alimentacao', 27.00, 'valor_fixo_diario', current_date);

-- 5. RLS: reembolso é aberto a QUALQUER funcionário autenticado (não
-- passa pelo sistema de módulos). Cada um só lê/escreve os próprios
-- relatórios em rascunho; aprovação restrita a módulo financeiro.

alter table cost_centers enable row level security;
create policy cost_centers_read on cost_centers for select to authenticated using (true);
create policy cost_centers_write on cost_centers for all to authenticated
  using (has_permission('reimbursement_reports', 'write'))
  with check (has_permission('reimbursement_reports', 'write'));

alter table team_cost_allocations enable row level security;
create policy team_cost_allocations_read on team_cost_allocations for select to authenticated using (true);
create policy team_cost_allocations_write on team_cost_allocations for all to authenticated
  using (has_permission('reimbursement_reports', 'write'))
  with check (has_permission('reimbursement_reports', 'write'));

alter table reimbursement_reports enable row level security;
create policy reimbursement_reports_own on reimbursement_reports for select to authenticated
  using (profile_id = auth.uid() or has_permission('reimbursement_reports', 'read'));
create policy reimbursement_reports_insert_own on reimbursement_reports for insert to authenticated
  with check (profile_id = auth.uid());
create policy reimbursement_reports_update_own_draft on reimbursement_reports for update to authenticated
  using (profile_id = auth.uid() and status = 'rascunho')
  with check (profile_id = auth.uid() and status in ('rascunho', 'enviado'));
create policy reimbursement_reports_approve on reimbursement_reports for update to authenticated
  using (has_permission('reimbursement_reports', 'write'))
  with check (has_permission('reimbursement_reports', 'write'));

alter table reimbursement_items enable row level security;
create policy reimbursement_items_via_report on reimbursement_items for all to authenticated
  using (exists (
    select 1 from reimbursement_reports r where r.id = reimbursement_items.report_id
    and (r.profile_id = auth.uid() or has_permission('reimbursement_reports', 'read'))
  ))
  with check (exists (
    select 1 from reimbursement_reports r where r.id = reimbursement_items.report_id
    and r.profile_id = auth.uid() and r.status = 'rascunho'
  ));

alter table reimbursement_rate_rules enable row level security;
create policy reimbursement_rate_rules_read on reimbursement_rate_rules for select to authenticated using (true);
create policy reimbursement_rate_rules_write on reimbursement_rate_rules for all to authenticated
  using (has_permission('reimbursement_reports', 'write'))
  with check (has_permission('reimbursement_reports', 'write'));

-- 6. Recurso/permissão pro módulo financeiro
insert into resources (key, label) values ('reimbursement_reports', 'Reembolsos')
  on conflict (key) do nothing;
insert into permissions (module_code, resource_key, can_read, can_write)
values ('financeiro', 'reimbursement_reports', true, true);
