-- ============================================================
-- 029_close_deal_function.sql
-- close_deal(): fecha um negócio numa transação atômica só (função
-- plpgsql = uma única transação implícita) — evita escrita parcial se
-- algo falhar no meio (ex.: cria a SPE mas não consegue criar o
-- contrato). Atualiza dados jurídicos do cliente, cria/atualiza a SPE
-- (billing_entities), copia a proposta mais recente pra um contrato,
-- marca a proposta como aceita e o projeto como fechado_ganho.
--
-- security definer: os INSERT/UPDATE internos rodam com o dono da
-- função, ignorando RLS de clients/billing_entities/contracts/proposals/
-- projects — mesmo padrão de has_permission()/profile_display_name().
-- auth.uid() dentro da função continua resolvendo pro usuário real que
-- chamou via RPC (request.jwt.claims é GUC de sessão, não muda com
-- security definer), por isso o `has_permission('projects', 'write')` no
-- início checa a permissão de quem chamou de verdade, não da função.
--
-- ROLLBACK:
--   revoke execute on function close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid) from authenticated;
--   drop function if exists close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid);
-- ============================================================

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
as $$
declare
  v_client_id uuid;
  v_proposal record;
  v_contract_code text;
  v_contract_id uuid;
begin
  if not has_permission('projects', 'write') then
    raise exception 'Sem permissão para fechar negócio';
  end if;

  select client_id into v_client_id from projects where id = p_project_id;
  if v_client_id is null then
    raise exception 'Projeto sem cliente vinculado';
  end if;

  update clients set
    legal_name = p_client_legal_name,
    cnpj = p_client_cnpj,
    address = p_client_address,
    legal_rep_name = p_legal_rep_name,
    legal_rep_cpf = p_legal_rep_cpf,
    legal_rep_role = p_legal_rep_role
  where id = v_client_id;

  insert into billing_entities (project_id, legal_name, cnpj, address)
  values (p_project_id, p_spe_legal_name, p_spe_cnpj, p_spe_address)
  on conflict (project_id) do update set
    legal_name = excluded.legal_name,
    cnpj = excluded.cnpj,
    address = excluded.address;

  select * into v_proposal from proposals
  where project_id = p_project_id
  order by version desc limit 1;

  if v_proposal is null then
    raise exception 'Nenhuma proposta encontrada para este projeto';
  end if;

  v_contract_code := lpad(v_proposal.version::text, 2, '0');

  insert into contracts (
    project_id, contract_code, contract_label, service_type_id,
    payment_type, fee_value, installments_count, signed_date, start_date, status
  ) values (
    p_project_id, v_contract_code,
    (select name from service_types where id = v_proposal.service_type_id),
    v_proposal.service_type_id, v_proposal.payment_type, v_proposal.value,
    v_proposal.installments_count, current_date, current_date, 'ativo'
  ) returning id into v_contract_id;

  update proposals set status = 'aceita' where id = v_proposal.id;
  update projects set pipeline_stage = 'fechado_ganho', team_id = p_team_id
  where id = p_project_id;

  return v_contract_id;
end;
$$;

grant execute on function close_deal(uuid,text,text,text,text,text,text,text,text,text,uuid) to authenticated;
