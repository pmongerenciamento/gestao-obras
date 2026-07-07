-- ============================================================
-- 013_alter_projects_add_client.sql
-- ROLLBACK:
--   drop index if exists idx_projects_client_code;
--   alter table projects drop column if exists project_code;
--   alter table projects drop column if exists client_id;
-- ============================================================
alter table projects add column client_id uuid references clients(id);
alter table projects add column project_code varchar(2);

create unique index idx_projects_client_code
  on projects (client_id, project_code)
  where client_id is not null and project_code is not null;
