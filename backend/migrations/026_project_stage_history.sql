-- ============================================================
-- 026_project_stage_history.sql
-- Histórico de mudanças de pipeline_stage por projeto: a cada UPDATE de
-- projects.pipeline_stage, fecha a linha aberta (exited_at) e abre uma
-- nova via trigger. Backfill dá aos projetos existentes uma linha
-- inicial usando created_at como aproximação de entered_at.
--
-- ROLLBACK:
--   drop policy if exists project_stage_history_read on project_stage_history;
--   alter table project_stage_history disable row level security;
--   drop trigger if exists trg_log_pipeline_stage_insert on projects;
--   drop function if exists log_pipeline_stage_insert();
--   drop trigger if exists trg_log_pipeline_stage_change on projects;
--   drop function if exists log_pipeline_stage_change();
--   drop index if exists idx_project_stage_history_open;
--   drop table if exists project_stage_history;
-- ============================================================

create table project_stage_history (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id),
  stage text not null,
  entered_at timestamptz not null default now(),
  exited_at timestamptz
);

create index idx_project_stage_history_open
  on project_stage_history (project_id)
  where exited_at is null;

-- PENDÊNCIA DE BAIXA PRIORIDADE (registrada em docs/sessao-atual.md, item
-- 115, 2026-07-09): esta função quebra com NotNullViolationError se
-- new.pipeline_stage for null (project_stage_history.stage é not null).
-- Não é problema hoje porque nenhum caminho do app seta pipeline_stage pra
-- null. Se isso mudar, adicionar `if new.pipeline_stage is null then return
-- new; end if;` no início do corpo, antes do IF abaixo.
create or replace function log_pipeline_stage_change()
returns trigger as $$
begin
  if new.pipeline_stage is distinct from old.pipeline_stage then
    update project_stage_history
      set exited_at = now()
      where project_id = new.id and exited_at is null;
    insert into project_stage_history (project_id, stage, entered_at)
      values (new.id, new.pipeline_stage, now());
  end if;
  return new;
end;
$$ language plpgsql security definer;

create trigger trg_log_pipeline_stage_change
  after update of pipeline_stage on projects
  for each row
  execute function log_pipeline_stage_change();

create or replace function log_pipeline_stage_insert()
returns trigger as $$
begin
  insert into project_stage_history (project_id, stage, entered_at)
    values (new.id, coalesce(new.pipeline_stage, 'prospect'), new.created_at);
  return new;
end;
$$ language plpgsql security definer;

create trigger trg_log_pipeline_stage_insert
  after insert on projects
  for each row
  execute function log_pipeline_stage_insert();

-- Backfill: projetos já existentes ganham uma linha inicial usando
-- created_at como aproximação de entered_at (não sabemos quando cada
-- um de fato entrou na etapa atual, é a melhor aproximação retroativa
-- possível).
insert into project_stage_history (project_id, stage, entered_at)
select id, coalesce(pipeline_stage, 'prospect'), created_at
from projects
where id not in (select project_id from project_stage_history);

-- RLS: leitura segue a mesma regra de projects (has_permission ou
-- dono); escrita só pelo trigger (security definer), sem policy de
-- insert/update direta.
alter table project_stage_history enable row level security;
create policy project_stage_history_read on project_stage_history
  for select to authenticated
  using (has_permission('projects', 'read') or exists (
    select 1 from projects where id = project_stage_history.project_id and owner_id = auth.uid()
  ));
