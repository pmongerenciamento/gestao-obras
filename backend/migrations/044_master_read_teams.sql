-- ============================================================
-- 044_master_read_teams.sql
-- Leitura de teams para o master, independente de módulo.
--
-- CAUSA: team_members já está coberto: team_members_write_master (043) é
-- "for all", e uma policy "for all" vale também para SELECT, então o
-- master lê todas as linhas de team_members desde a 043. O único buraco de
-- leitura do master é em teams: tanto teams_read quanto teams_write (023)
-- ainda dependem do catálogo (has_permission('teams', ...)), e no catálogo
-- só o módulo financeiro tem acesso a teams. Um master sem financeiro
-- conseguiria gravar em team_members, mas não listar os times, e a tela de
-- gestão de acesso em /usuarios quebraria.
--
-- O QUE FAZ: cria uma policy de SELECT em teams, só para authenticated,
-- com using (public.is_master()) (função da 043). É aditivo: policies
-- permissivas se somam por OR, então teams_read e teams_write continuam
-- exatamente como estão, e quem já lia (módulo financeiro) continua lendo.
-- Não abre nada para não-master nem para anon (is_master() não é
-- executável por anon, e a policy é só "to authenticated").
-- has_permission() e o catálogo não mudam.
--
-- ROLLBACK:
--   drop policy if exists teams_select_master on public.teams;
-- ============================================================

create policy teams_select_master on public.teams
  for select to authenticated
  using (public.is_master());
