-- ============================================================
-- 048_split_retroactive_master_only.sql
-- p_allow_retroactive de set_contract_splits passa a ser exclusivo do master.
--
-- O QUE FAZ:
--   set_contract_splits(uuid, date, jsonb, boolean) (create or replace com o
--   corpo da 047 e um bloco "048:" a mais): se p_allow_retroactive = true e
--   o usuário logado não for master (public.is_master(), da 043), recusa com
--   42501 antes de tocar no contrato. Vale mesmo que a janela da versão não
--   tenha parcela travada. Sem retroativo, nada muda: financeiro não master
--   continua gravando versões e continua recebendo 55000 quando a mudança
--   reatribuiria parcela emitida ou recebida.
--   O bloco fica logo depois da validação de p_allow_retroactive nulo: quem
--   não tem a permissão de escrita nos splits continua sendo recusado antes,
--   com o mesmo 42501. is_master() lê auth.uid() da requisição, então olha o
--   usuário que chamou, mesmo com set_contract_splits rodando como o dono.
--   create or replace mantém dono e privilégios da 047 (anon e PUBLIC sem
--   EXECUTE, authenticated com EXECUTE); search_path continua vazio.
--
-- NÃO FAZ: não muda o catálogo de permissões, a tabela nem as outras
-- funções. A regra de cobertura (não deixar parcela sem regra) continua
-- valendo também para o master.
--
-- ROLLBACK:
--   reaplicar a seção 4 da 047 (create function public.set_contract_splits
--   ...), trocando "create function" por "create or replace function" e sem
--   o "drop function" da assinatura antiga. Privilégios ficam como estão.
-- ============================================================

create or replace function public.set_contract_splits(
  p_contract_id uuid,
  p_valid_from date,
  p_splits jsonb,
  p_allow_retroactive boolean default false)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_item jsonb;
  v_idx integer := 0;
  v_kind text;
  v_team uuid;
  v_scope text;
  v_pct numeric;
  v_sum numeric := 0;
  v_next date;
  v_locked integer;
  v_rows integer;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not public.has_permission('contract_revenue_splits', 'write') then
    raise exception 'Sem permissão para alterar a divisão de receita do contrato'
      using errcode = '42501';
  end if;

  if p_contract_id is null then
    raise exception 'p_contract_id é obrigatório' using errcode = '22004';
  end if;
  if p_valid_from is null or extract(day from p_valid_from) <> 1 then
    raise exception 'p_valid_from é obrigatório e deve ser o dia 1 do mês' using errcode = '22023';
  end if;
  if p_splits is null or jsonb_typeof(p_splits) <> 'array' then
    raise exception 'p_splits deve ser uma lista JSON (use [] para remover a versão)'
      using errcode = '22023';
  end if;
  if p_allow_retroactive is null then
    raise exception 'p_allow_retroactive não pode ser nulo' using errcode = '22004';
  end if;

  -- 048: retroativo só para o master (is_master() lê auth.uid() da requisição)
  if p_allow_retroactive and not public.is_master() then
    raise exception 'p_allow_retroactive = true é exclusivo do master'
      using errcode = '42501';
  end if;

  perform 1 from public.contracts where id = p_contract_id for update;
  if not found then
    raise exception 'contrato % não encontrado', p_contract_id using errcode = 'P0002';
  end if;

  for v_item in select value from jsonb_array_elements(p_splits) loop
    v_idx := v_idx + 1;

    if jsonb_typeof(v_item) <> 'object' then
      raise exception 'item %: deve ser um objeto JSON', v_idx using errcode = '22023';
    end if;

    v_kind := v_item ->> 'share_kind';
    if v_kind is null or v_kind not in ('dono', 'a_parte') then
      raise exception 'item %: share_kind deve ser dono ou a_parte', v_idx using errcode = '22023';
    end if;

    v_scope := btrim(coalesce(v_item ->> 'scope', ''));
    if v_scope = '' then
      raise exception 'item %: scope é obrigatório', v_idx using errcode = '22023';
    end if;

    begin
      v_team := nullif(v_item ->> 'team_id', '')::uuid;
      v_pct := (v_item ->> 'percentage')::numeric;
    exception when invalid_text_representation then
      raise exception 'item %: team_id ou percentage em formato inválido', v_idx using errcode = '22023';
    end;

    if v_kind = 'dono' and v_team is null then
      raise exception 'item %: team_id é obrigatório na fatia do dono', v_idx using errcode = '22023';
    end if;

    if v_team is not null and not exists (select 1 from public.teams where id = v_team) then
      raise exception 'item %: time % não existe', v_idx, v_team using errcode = '23503';
    end if;

    if v_pct is null or v_pct <= 0 or v_pct > 100 or v_pct <> round(v_pct, 2) then
      raise exception 'item %: percentage deve ser maior que 0, no máximo 100 e com até 2 casas', v_idx
        using errcode = '22023';
    end if;

    v_sum := v_sum + v_pct;
  end loop;

  if v_idx > 0 and v_sum <> 100 then
    raise exception 'a soma dos percentuais deve ser 100 (veio %)', v_sum using errcode = '23514';
  end if;

  -- remover uma versão que não existe: nada a fazer
  if v_idx = 0 and not exists (select 1 from public.contract_revenue_splits
                                where contract_id = p_contract_id and valid_from = p_valid_from) then
    return 0;
  end if;

  -- janela da versão: de p_valid_from até a próxima versão do contrato
  select min(valid_from) into v_next
    from public.contract_revenue_splits
   where contract_id = p_contract_id and valid_from > p_valid_from;

  -- regra a: não reatribui parcela emitida ou recebida sem autorização explícita
  if not p_allow_retroactive then
    select count(*) into v_locked
      from public.contract_installments
     where contract_id = p_contract_id
       and status in ('emitida', 'recebida')
       and competencia_month >= p_valid_from
       and (v_next is null or competencia_month < v_next);
    if v_locked > 0 then
      raise exception 'a versão de % reatribuiria % parcela(s) emitida(s) ou recebida(s) até %: use p_allow_retroactive => true se a mudança retroativa for intencional',
        p_valid_from, v_locked, coalesce(v_next::text, 'o fim do contrato')
        using errcode = '55000';
    end if;
  end if;

  delete from public.contract_revenue_splits
   where contract_id = p_contract_id and valid_from = p_valid_from;

  if v_idx = 0 then
    -- regra b: a remoção não pode deixar parcela sem regra vigente
    if exists (select 1 from public.contract_installments i
                where i.contract_id = p_contract_id
                  and not exists (select 1 from public.contract_revenue_splits s
                                   where s.contract_id = p_contract_id
                                     and s.valid_from <= i.competencia_month)) then
      raise exception 'remover a versão de % deixaria parcela(s) do contrato sem regra de divisão vigente',
        p_valid_from using errcode = '55000';
    end if;
    return 0;
  end if;

  insert into public.contract_revenue_splits (contract_id, valid_from, share_kind, team_id, scope, percentage)
  select p_contract_id,
         p_valid_from,
         e.x ->> 'share_kind',
         nullif(e.x ->> 'team_id', '')::uuid,
         btrim(e.x ->> 'scope'),
         (e.x ->> 'percentage')::numeric
  from jsonb_array_elements(p_splits) as e(x);

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;
