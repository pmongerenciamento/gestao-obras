-- ============================================================
-- 039_fix_catalog_rls_privileges.sql
-- Fecha escrita pública no catálogo de permissões (modules, resources,
-- permissions — criados na 023).
--
-- CAUSA RAIZ: a 023 criou as 3 tabelas sem RLS e sem revogar os grants
-- padrão do Supabase, que dão a anon e authenticated SELECT/INSERT/
-- UPDATE/DELETE em toda tabela nova do schema public. Com RLS
-- desligado nada filtra esses grants: qualquer um com a chave anon
-- (pública, vai no bundle do frontend) conseguia, via API REST e sem
-- login, inserir/alterar linhas em permissions — p.ex. dar can_write
-- em expenses/bank_transactions a um módulo qualquer e assim abrir o
-- financeiro pra quem não deveria ter acesso. Confirmado em staging
-- (2026-10-04) com has_table_privilege().
--
-- Por que staging e produção divergiam: produção tem um event trigger
-- de RLS automático (ensure_rls → rls_auto_enable(), ddl_command_end)
-- que staging não tem. Aplicada em produção, a 023 deixaria as 3
-- tabelas com RLS ligado e sem policy; em staging ficaram com RLS
-- desligado (a brecha acima). Esta migration deixa os dois ambientes
-- no mesmo estado explícito, independente do event trigger existir.
--
-- has_permission() NÃO depende disto: é security definer e roda como
-- postgres (dono das tabelas, bypassrls=true, sem force row level
-- security), então lê o catálogo com RLS ligado ou desligado.
--
-- Resultado:
--   - authenticated: só leitura (policy select using true)
--   - anon: nenhum privilégio
--   - escrita no catálogo só por migration/painel (postgres/service_role)
--
-- ROLLBACK (volta ao estado de staging pós-023 — REABRE a brecha,
-- só usar se algo essencial quebrar):
--   grant all on modules, permissions, resources to anon;
--   drop policy if exists modules_read on modules;
--   drop policy if exists permissions_read on permissions;
--   drop policy if exists resources_read on resources;
--   alter table modules disable row level security;
--   alter table permissions disable row level security;
--   alter table resources disable row level security;
-- ============================================================

alter table modules enable row level security;
alter table permissions enable row level security;
alter table resources enable row level security;

create policy modules_read on modules for select to authenticated using (true);
create policy permissions_read on permissions for select to authenticated using (true);
create policy resources_read on resources for select to authenticated using (true);

revoke all on modules, permissions, resources from anon;
