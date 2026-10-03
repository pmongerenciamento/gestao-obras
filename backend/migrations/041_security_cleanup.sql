-- ============================================================
-- 041_security_cleanup.sql
-- Fecha as pendências de segurança encontradas ao aplicar 011-040 em
-- produção (2026-10-04), mesmo padrão da 040:
--
--   1. close_deal() (029) e default_allocation_rule_for_profile() (035):
--      security definer, executáveis por anon via RPC (default do
--      Postgres/Supabase — as migrations só fizeram grant pra
--      authenticated, sem revogar public/anon). close_deal já barrava
--      anon pelo has_permission() interno; default_allocation_rule_for_
--      profile não tinha checagem e revelava a que time um usuário
--      pertence a partir do id. Revoga public/anon, mantém authenticated.
--   2. As 6 funções abaixo são security definer sem search_path fixo —
--      alerta conhecido do linter do Supabase. Fixa search_path = '' e,
--      por isso, qualifica com schema TODO nome de tabela/função do
--      corpo (com search_path vazio, nome sem schema quebra em tempo de
--      execução):
--        - has_permission() (023) e has_module_access() (019): incluídas
--          porque função sem search_path próprio HERDA o de quem chama —
--          com close_deal rodando com search_path vazio, has_permission()
--          deixava de achar profile_modules/permissions e close_deal
--          quebrava ("relation profile_modules does not exist"; pego no
--          teste em staging, 2026-10-04). Corrigir na origem resolve pra
--          qualquer chamador. Privilégios delas não mudam (pra anon
--          devolvem sempre false: auth.uid() é nulo).
--        - close_deal() (029), default_allocation_rule_for_profile()
--          (035), log_pipeline_stage_change/_insert() (026).
--      As de trigger não recebem revoke: o Postgres não permite chamar
--      função "returns trigger" diretamente, nem via RPC.
--
-- Os corpos são os mesmos das migrations 019/023/026/029/035, só com os
-- nomes qualificados (public.*). Funções do pg_catalog (now, lpad,
-- coalesce, current_date) continuam resolvendo sem qualificar.
--
-- ROLLBACK (reabre o acesso anônimo e remove o search_path fixo):
--   grant execute on function close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid) to public, anon;
--   grant execute on function default_allocation_rule_for_profile(uuid) to public, anon;
--   (e recriar as 4 funções conforme 026/029/035)
--   (e recriar has_permission/has_module_access conforme 023/019)
-- ============================================================

-- 0. Funções do catálogo de permissões (019/023) — primeiro, porque
--    close_deal e todas as policies dependem delas.
create or replace function has_module_access(module_name text)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.profile_modules
    where profile_id = auth.uid() and module = module_name
  );
$$;

create or replace function has_permission(p_resource_key text, p_action text)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1
    from public.profile_modules pm
    join public.permissions p on p.module_code = pm.module
    where pm.profile_id = auth.uid()
      and p.resource_key = p_resource_key
      and (
        (p_action = 'read' and p.can_read)
        or (p_action = 'write' and p.can_write)
      )
  );
$$;

-- 1. close_deal (029)
create or replace function close_deal(
  p_project_id uuid,
  p_client_legal_name text,
  p_client_cnpj text,
  p_client_address text,
  p_legal_rep_name text,
  p_legal_rep_cpf text,
  p_legal_rep_role text,
  p_spe_legal_name text,
  p_spe_cnpj text,
  p_spe_address text,
  p_team_id uuid
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_client_id uuid;
  v_proposal record;
  v_contract_code text;
  v_contract_id uuid;
begin
  if not public.has_permission('projects', 'write') then
    raise exception 'Sem permissão para fechar negócio';
  end if;

  select client_id into v_client_id from public.projects where id = p_project_id;
  if v_client_id is null then
    raise exception 'Projeto sem cliente vinculado';
  end if;

  update public.clients set
    legal_name = p_client_legal_name,
    cnpj = p_client_cnpj,
    address = p_client_address,
    legal_rep_name = p_legal_rep_name,
    legal_rep_cpf = p_legal_rep_cpf,
    legal_rep_role = p_legal_rep_role
  where id = v_client_id;

  insert into public.billing_entities (project_id, legal_name, cnpj, address)
  values (p_project_id, p_spe_legal_name, p_spe_cnpj, p_spe_address)
  on conflict (project_id) do update set
    legal_name = excluded.legal_name,
    cnpj = excluded.cnpj,
    address = excluded.address;

  select * into v_proposal from public.proposals
  where project_id = p_project_id
  order by version desc limit 1;

  if v_proposal is null then
    raise exception 'Nenhuma proposta encontrada para este projeto';
  end if;

  v_contract_code := lpad(v_proposal.version::text, 2, '0');

  insert into public.contracts (
    project_id, contract_code, contract_label, service_type_id,
    payment_type, fee_value, installments_count, signed_date, start_date, status
  ) values (
    p_project_id, v_contract_code,
    (select name from public.service_types where id = v_proposal.service_type_id),
    v_proposal.service_type_id, v_proposal.payment_type, v_proposal.value,
    v_proposal.installments_count, current_date, current_date, 'ativo'
  ) returning id into v_contract_id;

  update public.proposals set status = 'aceita' where id = v_proposal.id;
  update public.projects set pipeline_stage = 'fechado_ganho', team_id = p_team_id
  where id = p_project_id;

  return v_contract_id;
end;
$$;

revoke execute on function close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid) from public, anon;
grant execute on function close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid) to authenticated;

-- 2. default_allocation_rule_for_profile (035)
create or replace function default_allocation_rule_for_profile(p_profile_id uuid)
returns uuid
language plpgsql
security definer
stable
set search_path = ''
as $$
declare
  v_team_name text;
  v_rule_id uuid;
begin
  select t.name into v_team_name
  from public.team_members tm
  join public.teams t on t.id = tm.team_id
  where tm.profile_id = p_profile_id
  limit 1;

  if v_team_name = 'Carlos' then
    select id into v_rule_id from public.allocation_rules where name = 'Time Carlos 100%';
  elsif v_team_name = 'Weslley' then
    select id into v_rule_id from public.allocation_rules where name = 'Time Weslley 100%';
  else
    select id into v_rule_id from public.allocation_rules where name = 'Rateio Sócios 50/50 (Carlos/Weslley)';
  end if;

  return v_rule_id;
end;
$$;

revoke execute on function default_allocation_rule_for_profile(uuid) from public, anon;
grant execute on function default_allocation_rule_for_profile(uuid) to authenticated;

-- 3. Funções de trigger da 026 (só search_path; sem revoke, ver topo)
create or replace function log_pipeline_stage_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.pipeline_stage is distinct from old.pipeline_stage then
    update public.project_stage_history
      set exited_at = now()
      where project_id = new.id and exited_at is null;
    insert into public.project_stage_history (project_id, stage, entered_at)
      values (new.id, new.pipeline_stage, now());
  end if;
  return new;
end;
$$;

create or replace function log_pipeline_stage_insert()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.project_stage_history (project_id, stage, entered_at)
    values (new.id, coalesce(new.pipeline_stage, 'prospect'), new.created_at);
  return new;
end;
$$;
