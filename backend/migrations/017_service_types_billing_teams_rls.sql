-- ============================================================
-- 017_service_types_billing_teams_rls.sql
-- Habilita RLS em `service_types`, `teams`, `team_members` e
-- `billing_entities` (012/014/015_create_teams.sql não tinham nenhuma —
-- mesmo gap de 011_create_clients.sql, corrigido em 016_clients_rls.sql).
--
-- PENDÊNCIA IMPORTANTE (bloqueia o desenho original desta migration):
-- o plano original previa `auth.jwt() ->> 'department' = 'financeiro'`
-- para restringir escrita de teams/team_members e leitura+escrita de
-- billing_entities a um papel "financeiro". Esse claim NÃO existe no
-- projeto — não há Auth Hook customizado configurado no Supabase, nenhum
-- código lê/grava esse claim, e `profiles.system_role` (015) existe mas
-- nunca foi populado. Aplicar a policy com esse claim bloquearia todo
-- mundo, incluindo o time financeiro de verdade.
-- Fallback adotado (temporário, decisão do usuário 2026-07-08): as
-- policies que seriam department='financeiro' usam `to authenticated`
-- por enquanto, mantidas como policies SEPARADAS (não fundidas com as de
-- leitura) só pra virar um diff de uma linha quando o mecanismo de
-- papel/departamento existir de verdade. Efeito prático: billing_entities
-- (CNPJ + dados bancários) fica legível/editável por QUALQUER funcionário
-- autenticado até essa pendência ser resolvida — não é o modelo de
-- segurança desejado a longo prazo, só o intermediário menos pior do que
-- travar todo mundo.
--
-- ROLLBACK:
--   drop policy if exists service_types_all_authenticated on service_types;
--   drop policy if exists teams_select_authenticated on teams;
--   drop policy if exists teams_write_authenticated on teams;
--   drop policy if exists team_members_select_authenticated on team_members;
--   drop policy if exists team_members_write_authenticated on team_members;
--   drop policy if exists billing_entities_select_authenticated on billing_entities;
--   drop policy if exists billing_entities_write_authenticated on billing_entities;
--   alter table service_types disable row level security;
--   alter table teams disable row level security;
--   alter table team_members disable row level security;
--   alter table billing_entities disable row level security;
-- ============================================================

-- =========================================================
-- SERVICE_TYPES — catálogo compartilhado, mesmo padrão de clients (016):
-- qualquer funcionário autenticado lê e escreve.
-- =========================================================

alter table service_types enable row level security;

create policy service_types_all_authenticated on service_types
  for all
  to authenticated
  using (true)
  with check (true);

-- =========================================================
-- TEAMS — leitura liberada pra todo mundo autenticado; escrita seria
-- restrita a department='financeiro' (ver pendência no topo do arquivo).
-- Fallback atual: escrita também `to authenticated`.
-- =========================================================

alter table teams enable row level security;

create policy teams_select_authenticated on teams
  for select
  to authenticated
  using (true);

-- TODO: trocar `using (true)`/`with check (true)` abaixo por
-- `auth.jwt() ->> 'department' = 'financeiro'` quando esse claim existir.
create policy teams_write_authenticated on teams
  for all
  to authenticated
  using (true)
  with check (true);

-- =========================================================
-- TEAM_MEMBERS — mesma lógica de teams.
-- =========================================================

alter table team_members enable row level security;

create policy team_members_select_authenticated on team_members
  for select
  to authenticated
  using (true);

-- TODO: trocar `using (true)`/`with check (true)` abaixo por
-- `auth.jwt() ->> 'department' = 'financeiro'` quando esse claim existir.
create policy team_members_write_authenticated on team_members
  for all
  to authenticated
  using (true)
  with check (true);

-- =========================================================
-- BILLING_ENTITIES — CNPJ + dados bancários. Plano original: SEM policy
-- de leitura ampla, select e escrita restritos a department='financeiro'.
-- Fallback atual (claim inexistente, ver pendência no topo): select e
-- escrita ficam `to authenticated` — mais aberto do que o desejado,
-- revisar assim que houver um mecanismo real de papel/departamento.
-- =========================================================

alter table billing_entities enable row level security;

-- TODO: trocar `using (true)` abaixo por
-- `auth.jwt() ->> 'department' = 'financeiro'` quando esse claim existir.
create policy billing_entities_select_authenticated on billing_entities
  for select
  to authenticated
  using (true);

-- TODO: trocar `using (true)`/`with check (true)` abaixo por
-- `auth.jwt() ->> 'department' = 'financeiro'` quando esse claim existir.
create policy billing_entities_write_authenticated on billing_entities
  for all
  to authenticated
  using (true)
  with check (true);
