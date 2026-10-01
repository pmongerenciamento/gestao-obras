-- ============================================================
-- 027_projects_write_crm.sql
-- Libera UPDATE em `projects` pro módulo CRM (024 só tinha aberto
-- SELECT, de propósito — "CRM não deve editar dados de execução da
-- obra"). Motivado pelo drag-and-drop do board de pipeline
-- (/crm/pipeline): mover um card de etapa é escrita em
-- projects.pipeline_stage, e hoje só o dono do projeto pode escrever
-- (projects_owner_access) — sem esta policy, um usuário CRM que não é
-- dono arrasta o card na UI mas o UPDATE é silenciosamente filtrado
-- pelo RLS (0 linhas afetadas, sem erro).
--
-- Mesmo padrão row-level de clients_write/contracts_write/proposals_write
-- (023): a policy libera escrita na linha toda, não só em
-- pipeline_stage — Postgres RLS não restringe por coluna sem GRANT
-- column-level, que não é usado em nenhuma outra tabela deste app. A UI
-- é quem só expõe pipeline_stage pro CRM; confiança de aplicação, não
-- do banco, mesmo modelo já aceito nas outras 3 tabelas.
--
-- ROLLBACK:
--   drop policy if exists projects_update_crm on projects;
--   update permissions set can_write = false where module_code = 'crm' and resource_key = 'projects';
-- ============================================================

update permissions set can_write = true
where module_code = 'crm' and resource_key = 'projects';

create policy projects_update_crm on projects
  for update to authenticated
  using (has_permission('projects', 'write'))
  with check (has_permission('projects', 'write'));
