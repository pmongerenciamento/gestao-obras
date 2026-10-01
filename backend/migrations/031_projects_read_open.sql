-- ============================================================
-- 031_projects_read_open.sql
-- Libera leitura de `projects` pra QUALQUER usuário autenticado, sem
-- exigir módulo nenhum — motivado pelo select de projeto no item de
-- reembolso "Visita a Cliente"/"Visita Comercial" (030): reembolso não
-- segue o sistema de permissões por módulo, então um funcionário sem
-- o módulo CRM e que não é dono de nenhum projeto (ex.: RH,
-- administrativo) precisa conseguir listar projetos pra lançar esse
-- tipo de despesa.
--
-- RLS combina múltiplas policies do mesmo comando (SELECT) com OR
-- (mesma lógica de 024_projects_read_crm.sql), então isso só amplia
-- quem pode ler — não retira o acesso via projects_owner_access nem
-- projects_read_crm. A UI é quem decide quais colunas expor pra cada
-- tela (aqui, só id/name pro select do form de reembolso); RLS não
-- restringe por coluna sem GRANT column-level, mesmo modelo já aceito
-- em 027.
--
-- ROLLBACK:
--   drop policy if exists projects_read_authenticated on projects;
-- ============================================================

create policy projects_read_authenticated on projects
  for select to authenticated
  using (true);
