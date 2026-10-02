-- ============================================================
-- 035_default_allocation_rule.sql
-- Fase B (parte 1) do módulo Financeiro: função que resolve a regra
-- de rateio PADRÃO de um profile, a partir do time a que ele pertence
-- (team_members). Espelha a lógica que hoje está em team_cost_allocations
-- (migration 030), agora apontando para as allocation_rules nomeadas
-- (migration 034):
--   time Carlos           -> 'Time Carlos 100%'
--   time Weslley          -> 'Time Weslley 100%'
--   qualquer outro / nenhum time -> 'Rateio Sócios 50/50 (Carlos/Weslley)'
--
-- O código do Reembolso vai usar essa função para pré-preencher
-- reimbursement_items.allocation_rule_id (migration 034) na criação do
-- item. security definer: lê team_members/teams/allocation_rules
-- independentemente das policies do chamador.
--
-- ADITIVA: só cria função + grant, não altera tabela nenhuma.
--
-- ROLLBACK:
--   drop function if exists default_allocation_rule_for_profile(uuid);
-- ============================================================

create or replace function default_allocation_rule_for_profile(p_profile_id uuid)
returns uuid
language plpgsql
security definer
stable
as $$
declare
  v_team_name text;
  v_rule_id uuid;
begin
  select t.name into v_team_name
  from team_members tm
  join teams t on t.id = tm.team_id
  where tm.profile_id = p_profile_id
  limit 1;

  if v_team_name = 'Carlos' then
    select id into v_rule_id from allocation_rules where name = 'Time Carlos 100%';
  elsif v_team_name = 'Weslley' then
    select id into v_rule_id from allocation_rules where name = 'Time Weslley 100%';
  else
    select id into v_rule_id from allocation_rules where name = 'Rateio Sócios 50/50 (Carlos/Weslley)';
  end if;

  return v_rule_id;
end;
$$;

grant execute on function default_allocation_rule_for_profile(uuid) to authenticated;
