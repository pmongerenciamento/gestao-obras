-- ============================================================
-- 051_contract_billing_entity.sql
-- SPE do contrato (para a mesma SPE em projetos diferentes), função que
-- resolve a SPE de um contrato, bloqueio de INSERT de contrato já encerrado
-- pela API e comentário em contracts.document_lead_days.
--
-- REGRA: o tomador da nota é sempre a SPE (050). Hoje a SPE vem do projeto
-- (public.billing_entities, uma por projeto, project_id único). O contrato
-- passa a poder apontar para outra SPE já cadastrada, desde que ela seja do
-- mesmo projeto ou de um projeto do mesmo cliente (item 5); vazio continua
-- significando "a SPE do projeto do contrato".
--
-- O QUE FAZ:
--   1. public.contracts.billing_entity_id: uuid, aceita nulo, FK para
--      public.billing_entities(id) sem cascade (apagar uma SPE usada por
--      algum contrato é recusado). Índice parcial onde não é nulo.
--      Comentário: vazio = a SPE do projeto. Coluna nula sem default: o
--      ALTER só muda o catálogo, não reescreve a tabela. Nenhuma linha
--      existente é preenchida.
--   2. public.contract_billing_entity_id(p_contract_id uuid) returns uuid:
--      language sql, stable, security invoker, search_path vazio. Devolve
--      coalesce(contracts.billing_entity_id, a SPE do projeto do contrato);
--      nulo se o contrato não existir ou não houver SPE. SECURITY INVOKER:
--      a RLS de quem chama vale; sem leitura de contracts ou de
--      billing_entities (crm e financeiro têm as duas, 023) o resultado é
--      nulo, igual a "sem SPE". EXECUTE só para authenticated.
--   3. trg_contracts_guard_insert (BEFORE INSERT em contracts, função
--      própria public.fn_contracts_guard_insert, sem OLD): para quem chama
--      pela API (auth.uid() não nulo) recusa (42501) inserir contrato com
--      status 'encerrado' ou com termination_notice_date ou
--      termination_reason preenchidos (qualquer valor não nulo, inclusive
--      texto vazio). Migration e service role (auth.uid() nulo) passam, como
--      nos triggers da 043 e da 049. Fecha a brecha que a 049 deixou: o
--      trg_contracts_guard_close só olha UPDATE OF status. O close_deal
--      (security definer, mas com o auth.uid() da requisição) insere
--      contrato 'ativo' e sem dados de encerramento, então continua passando.
--      EXECUTE da função de trigger revogado de public, anon e
--      authenticated (não afeta o disparo).
--   4. comment on column public.contracts.document_lead_days: sem
--      significado documentado e sem uso (conferido em 2026-10-07; ver 050).
--   5. trg_contracts_guard_billing_entity (BEFORE INSERT OR UPDATE OF
--      billing_entity_id, project_id em contracts, por linha; função
--      public.fn_contracts_guard_billing_entity, security definer, search_path
--      vazio). Com billing_entity_id nulo não faz nada. Preenchido, só aceita
--      se a SPE é do mesmo projeto do contrato, ou se o projeto da SPE e o do
--      contrato têm o mesmo client_id, os dois não nulos; senão recusa com
--      23514. SPE inexistente passa pelo gatilho e é recusada pela FK
--      (23503). Vale para todos, inclusive migration e service role: é regra
--      de dado, não de API. security definer: precisa ler billing_entities e
--      projects inteiras, sem depender da RLS de quem grava. EXECUTE da
--      função de trigger revogado de public, anon e authenticated.
--      LIMITE: a regra é conferida quando o contrato é gravado; mudar depois
--      projects.client_id ou billing_entities.project_id não reconfere os
--      contratos que já apontam para a SPE.
--
-- NÃO FAZ (fica para as próximas): visão de completude (pronto para operar
-- e pronto para emitir); views do DRE; cópia de campos no close_deal (por
-- último).
-- PENDENTE (close_deal, CNPJ já cadastrado em outro projeto): o close_deal
-- faz upsert em billing_entities pelo project_id, mas billing_entities.cnpj é
-- único (014); fechar negócio em um segundo projeto informando o CNPJ de uma
-- SPE já cadastrada falha com 23505. Esta migration não muda isso: a mesma
-- SPE em outro projeto entra apontando contracts.billing_entity_id para a SPE
-- existente (mesmo cliente, item 5), e o fluxo do close_deal para esse caso
-- (reaproveitar a SPE pelo CNPJ em vez de criar outra) fica para a migration
-- dele.
--
-- ROLLBACK (na ordem; apaga a SPE escolhida nos contratos):
--   drop trigger if exists trg_contracts_guard_billing_entity on public.contracts;
--   drop trigger if exists trg_contracts_guard_insert on public.contracts;
--   drop function if exists public.fn_contracts_guard_billing_entity();
--   drop function if exists public.fn_contracts_guard_insert();
--   drop function if exists public.contract_billing_entity_id(uuid);
--   comment on column public.contracts.document_lead_days is null;
--   drop index if exists public.idx_contracts_billing_entity;
--   alter table public.contracts drop column if exists billing_entity_id;
-- ============================================================

-- 1. SPE do contrato
alter table public.contracts
  add column billing_entity_id uuid references public.billing_entities(id);

create index idx_contracts_billing_entity on public.contracts (billing_entity_id)
  where billing_entity_id is not null;

comment on column public.contracts.billing_entity_id is
  'SPE tomadora da nota deste contrato. Vazio = a SPE do projeto do contrato '
  '(billing_entities.project_id = contracts.project_id). Resolver com '
  'public.contract_billing_entity_id(id) (051).';

-- 2. SPE efetiva de um contrato
create function public.contract_billing_entity_id(p_contract_id uuid)
returns uuid
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(
           c.billing_entity_id,
           (select be.id from public.billing_entities be where be.project_id = c.project_id))
  from public.contracts c
  where c.id = p_contract_id;
$$;

revoke execute on function public.contract_billing_entity_id(uuid) from public, anon;
grant execute on function public.contract_billing_entity_id(uuid) to authenticated;

-- 3. Não inserir contrato já encerrado pela API
-- Mesmo padrão do trg_contracts_guard_close da 049: com auth.uid() nulo
-- (migration, service role) não barra.
create function public.fn_contracts_guard_insert()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if auth.uid() is null then
    return new;
  end if;

  if new.status = 'encerrado' then
    raise exception 'contrato não pode ser criado já encerrado: crie ativo e encerre pela função close_contract'
      using errcode = '42501';
  end if;

  if new.termination_notice_date is not null or new.termination_reason is not null then
    raise exception 'dados de encerramento (termination_notice_date, termination_reason) só são gravados pela função close_contract'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_contracts_guard_insert() from public, anon, authenticated;

create trigger trg_contracts_guard_insert
  before insert on public.contracts
  for each row
  execute function public.fn_contracts_guard_insert();

-- 4. document_lead_days
comment on column public.contracts.document_lead_days is
  'Sem significado documentado e sem uso no backend ou no frontend '
  '(conferido em 2026-10-07; 051). A emissão automática define o campo certo.';

-- 5. SPE do contrato: do mesmo projeto ou de projeto do mesmo cliente
-- Regra de dado: vale para todos, inclusive migration e service role.
-- security definer: lê billing_entities e projects inteiras, sem depender
-- da RLS de quem grava (uma linha escondida faria a regra falhar à toa).
create function public.fn_contracts_guard_billing_entity()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_be_project uuid;
  v_be_client uuid;
  v_contract_client uuid;
begin
  if new.billing_entity_id is null then
    return new;
  end if;

  select be.project_id, p.client_id
    into v_be_project, v_be_client
  from public.billing_entities be
  join public.projects p on p.id = be.project_id
  where be.id = new.billing_entity_id;

  -- SPE inexistente: a FK recusa logo depois (23503)
  if not found then
    return new;
  end if;

  if v_be_project = new.project_id then
    return new;
  end if;

  select p.client_id into v_contract_client
  from public.projects p
  where p.id = new.project_id;

  if v_be_client is not null and v_contract_client is not null and v_be_client = v_contract_client then
    return new;
  end if;

  raise exception 'SPE % não pode ser a tomadora deste contrato: ela não é do projeto do contrato nem de um projeto do mesmo cliente (os dois projetos precisam ter client_id preenchido e igual)',
    new.billing_entity_id
    using errcode = '23514';
end;
$$;

revoke execute on function public.fn_contracts_guard_billing_entity() from public, anon, authenticated;

create trigger trg_contracts_guard_billing_entity
  before insert or update of billing_entity_id, project_id on public.contracts
  for each row
  execute function public.fn_contracts_guard_billing_entity();
