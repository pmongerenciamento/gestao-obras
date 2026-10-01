-- ============================================================
-- 024_projects_read_crm.sql
-- Libera leitura de `projects` pro módulo CRM via o catálogo de
-- permissions (023) — sem isso, o dashboard do CRM (funil de vendas,
-- ranking por owner) só enxergaria os projetos do próprio usuário
-- logado, porque a única policy existente em `projects`
-- (`projects_owner_access`, de 001_initial_schema.sql) é
-- `owner_id = auth.uid()`.
--
-- Confirmado via `select tablename, policyname, cmd, qual from
-- pg_policies where tablename = 'projects'` antes de escrever esta
-- migration: só existe `projects_owner_access` (ALL, owner_id =
-- auth.uid()). A policy nova abaixo é adicionada, não substitui essa
-- — RLS combina múltiplas policies do mesmo comando (aqui, SELECT)
-- com OR, então isso só amplia quem pode ler, sem tirar o acesso do
-- dono via `projects_owner_access`. Sem policy de escrita nova: CRM
-- não deve editar dados de execução da obra (leitura só).
--
-- ROLLBACK:
--   drop policy if exists projects_read_crm on projects;
--   delete from permissions where module_code = 'crm' and resource_key = 'projects';
-- ============================================================

insert into resources (key, label) values ('projects', 'Projetos')
  on conflict (key) do nothing;

insert into permissions (module_code, resource_key, can_read, can_write)
values ('crm', 'projects', true, false);

create policy projects_read_crm on projects
  for select to authenticated
  using (has_permission('projects', 'read'));
