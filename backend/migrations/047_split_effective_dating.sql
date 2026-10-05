-- ============================================================
-- 047_split_effective_dating.sql
-- Vigência por mês na regra de divisão de receita do contrato.
--
-- REGRA: cada versão da divisão vale a partir de valid_from (dia 1 do mês)
-- até a próxima versão do mesmo contrato. A parcela é alocada pela versão
-- com o maior valid_from <= competencia_month da parcela (alocação nas
-- views, que são a 049).
--
-- O QUE FAZ:
--   1. Aborta se public.contract_revenue_splits tiver qualquer linha (a
--      coluna nova é obrigatória e não há como inventar a vigência de
--      linhas existentes).
--   2. contract_revenue_splits.valid_from date not null, check de dia 1;
--      a unicidade contract_revenue_splits_unique passa a incluir
--      valid_from (unique nulls not distinct, como na 045).
--   3. fn_contract_revenue_splits_sum_100 (create or replace, mesmos
--      atributos): soma 100 por (contract_id, valid_from). O constraint
--      trigger trg_contract_revenue_splits_sum_100 aponta para a função
--      pelo oid e não muda; create or replace mantém dono e privilégios
--      (o revoke de public, anon e authenticated da 045 continua valendo).
--   4. set_contract_splits: sai a assinatura (uuid, jsonb) e entra
--      set_contract_splits(p_contract_id uuid, p_valid_from date,
--      p_splits jsonb, p_allow_retroactive boolean default false). Grava
--      UMA versão: apaga e reinsere só as linhas daquele contrato e daquele
--      valid_from. Mesmas validações da 045 (itens, team_id na fatia do
--      dono, percentual com até 2 casas, soma 100). Lista vazia remove a
--      versão. Regras novas (errcode 55000):
--        a) recusa se a janela da versão (competência >= valid_from e <
--           próxima versão do contrato) tiver parcela 'emitida' ou
--           'recebida', a menos que p_allow_retroactive = true. A checagem
--           é conservadora: recusa mesmo que a versão regravada seja igual
--           à atual.
--        b) recusa a remoção que deixaria alguma parcela do contrato sem
--           regra vigente (inclui remover a única versão de um contrato
--           que já tem parcelas). p_allow_retroactive não libera isto.
--   5. generate_contract_installments e extend_recurring_installments
--      (create or replace com o corpo da 046 e um bloco "047:" a mais):
--      recusam com 55000 quando o contrato não tem versão de regra com
--      valid_from <= mês do vencimento da primeira parcela a gerar. Na
--      extensão a checagem é feita antes da primeira inserção, então uma
--      chamada que não teria nada a criar continua devolvendo 0.
--
-- NÃO FAZ: views do DRE (049); ciclo de vida do contrato, parcelado e
-- encerramento (048); transfer_project_portfolio (migration própria);
-- close_deal não muda.
--
-- ROLLBACK (na ordem; apaga todas as versões de divisão gravadas):
--   drop function if exists public.set_contract_splits(uuid, date, jsonb, boolean);
--   delete from public.contract_revenue_splits;
--   alter table public.contract_revenue_splits drop constraint contract_revenue_splits_unique;
--   alter table public.contract_revenue_splits
--     add constraint contract_revenue_splits_unique
--     unique nulls not distinct (contract_id, share_kind, team_id, scope);
--   alter table public.contract_revenue_splits drop constraint contract_revenue_splits_valid_from_day1;
--   alter table public.contract_revenue_splits drop column valid_from;
--   -- reaplicar, copiando dos arquivos:
--   --   045 seção 8 (fn_contract_revenue_splits_sum_100, create or replace)
--   --   045 seção 9 (set_contract_splits(uuid, jsonb) + revoke/grant)
--   --   046 seções 4 e 5 (generate_contract_installments e
--   --   extend_recurring_installments, trocando create por create or replace)
-- ============================================================

-- 1. Só roda com a tabela vazia
do $$
begin
  if exists (select 1 from public.contract_revenue_splits) then
    raise exception 'contract_revenue_splits tem linhas: a 047 exige a tabela vazia (valid_from é obrigatório)';
  end if;
end;
$$;

-- 2. valid_from e unicidade por versão
alter table public.contract_revenue_splits add column valid_from date not null;

alter table public.contract_revenue_splits
  add constraint contract_revenue_splits_valid_from_day1 check (extract(day from valid_from) = 1);

alter table public.contract_revenue_splits drop constraint contract_revenue_splits_unique;
alter table public.contract_revenue_splits
  add constraint contract_revenue_splits_unique
  unique nulls not distinct (contract_id, valid_from, share_kind, team_id, scope);

comment on column public.contract_revenue_splits.valid_from is
  'Início da vigência da versão (dia 1 do mês). Vale até a próxima versão do mesmo contrato; '
  'a parcela usa a versão com o maior valid_from <= competencia_month. Desde a 047.';

-- 3. Soma 100 por (contract_id, valid_from)
create or replace function public.fn_contract_revenue_splits_sum_100()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_contracts uuid[] := '{}';
  v_froms date[] := '{}';
  v_count integer;
  v_sum numeric;
  i integer;
begin
  if tg_op in ('INSERT', 'UPDATE') then
    v_contracts := v_contracts || new.contract_id;
    v_froms := v_froms || new.valid_from;
  end if;
  if tg_op in ('UPDATE', 'DELETE') then
    v_contracts := v_contracts || old.contract_id;
    v_froms := v_froms || old.valid_from;
  end if;

  for i in 1 .. coalesce(array_length(v_contracts, 1), 0) loop
    select count(*), coalesce(sum(percentage), 0)
      into v_count, v_sum
      from public.contract_revenue_splits
     where contract_id = v_contracts[i] and valid_from = v_froms[i];

    if v_count > 0 and v_sum <> 100 then
      raise exception 'divisão de receita do contrato % (vigência %) soma % (deve somar 100)',
        v_contracts[i], v_froms[i], v_sum
        using errcode = '23514';
    end if;
  end loop;

  return null;
end;
$$;

-- 4. set_contract_splits com vigência
drop function public.set_contract_splits(uuid, jsonb);

-- p_splits: lista JSON de objetos
--   {"share_kind": "dono"|"a_parte", "team_id": "<uuid>"|null,
--    "scope": "<texto>", "percentage": <número com até 2 casas>}
-- Devolve quantas linhas ficaram gravadas na versão (0 quando remove).
create function public.set_contract_splits(
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

revoke execute on function public.set_contract_splits(uuid, date, jsonb, boolean) from public, anon;
grant execute on function public.set_contract_splits(uuid, date, jsonb, boolean) to authenticated;

-- 5a. generate_contract_installments: corpo da 046 + bloco 047
create or replace function public.generate_contract_installments(
  p_contract_id uuid,
  p_revenue_type text default null,
  p_destination_account text default 'inter_pj')
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_c record;
  v_type text;
  v_has_readj boolean;
  v_amount numeric(14,2);
  v_total integer;
  v_next_number integer;
  v_due date;
  v_prev date := null;
  v_created integer := 0;
  n integer;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not public.has_permission('contract_installments', 'write') then
    raise exception 'Sem permissão para gerar parcelas' using errcode = '42501';
  end if;

  select c.id, c.status, c.payment_type, c.fee_value, c.first_due_date, c.start_date, c.end_date,
         c.readjustment_index, c.readjustment_cycle_months, st.default_revenue_type
    into v_c
    from public.contracts c
    left join public.service_types st on st.id = c.service_type_id
   where c.id = p_contract_id
     for update of c;
  if not found then
    raise exception 'contrato % não encontrado', p_contract_id using errcode = 'P0002';
  end if;

  if v_c.status = 'encerrado' then
    raise exception 'contrato encerrado: não gera parcelas' using errcode = '55000';
  end if;
  if v_c.payment_type = 'parcelado' then
    raise exception 'geração do parcelado bloqueada até confirmar o sentido de fee_value (total ou por parcela); lance as parcelas como avulsas'
      using errcode = '0A000';
  end if;
  if v_c.first_due_date is null then
    raise exception 'contrato sem first_due_date: preencha o 1º vencimento antes de gerar' using errcode = '55000';
  end if;
  if exists (select 1 from public.contract_installments
              where contract_id = p_contract_id and origin = 'projetada') then
    raise exception 'contrato já tem parcelas projetadas: use extend_recurring_installments' using errcode = '55000';
  end if;

  v_type := coalesce(nullif(btrim(p_revenue_type), ''), v_c.default_revenue_type);
  if v_type is null then
    raise exception 'informe p_revenue_type: o tipo de serviço do contrato não tem tipo de receita padrão'
      using errcode = '22023';
  end if;

  -- 047: exige versão da regra de divisão vigente no mês do 1º vencimento
  if not exists (select 1 from public.contract_revenue_splits
                  where contract_id = p_contract_id
                    and valid_from <= date_trunc('month', v_c.first_due_date::timestamp)::date) then
    raise exception 'contrato sem regra de divisão de receita vigente em % (mês do 1º vencimento): grave uma versão com set_contract_splits antes de gerar',
      date_trunc('month', v_c.first_due_date::timestamp)::date
      using errcode = '55000';
  end if;

  v_amount := round(v_c.fee_value, 2);
  v_has_readj := v_c.readjustment_index is not null and btrim(v_c.readjustment_index) <> ''
                 and coalesce(v_c.readjustment_cycle_months, 0) > 0;
  v_total := case v_c.payment_type when 'parcela_unica' then 1 else 12 end;

  -- avulsas já lançadas ocupam números: continua depois delas
  select coalesce(max(installment_number), 0) + 1 into v_next_number
    from public.contract_installments where contract_id = p_contract_id;

  for n in 0 .. v_total - 1 loop
    v_due := (v_c.first_due_date + make_interval(months => n))::date;
    exit when v_c.payment_type = 'mensal_recorrente' and v_c.end_date is not null and v_due > v_c.end_date;

    insert into public.contract_installments (
      contract_id, installment_number, revenue_type, origin, due_date,
      base_amount, readjustment_factor, expected_amount, status,
      is_revision_point, destination_account, created_by
    ) values (
      p_contract_id, v_next_number + v_created, v_type, 'projetada', v_due,
      v_amount, 1, v_amount, 'projetada',
      v_has_readj and public.fn_contract_is_revision_point(
        v_c.start_date, v_c.readjustment_cycle_months, v_prev, v_due),
      p_destination_account, v_uid
    );

    v_prev := v_due;
    v_created := v_created + 1;
  end loop;

  if v_created = 0 then
    raise exception 'nenhuma parcela gerada: end_date anterior ao first_due_date' using errcode = '22023';
  end if;

  return v_created;
end;
$$;

-- 5b. extend_recurring_installments: corpo da 046 + bloco 047
create or replace function public.extend_recurring_installments(p_contract_id uuid)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_c record;
  v_ref record;
  v_has_readj boolean;
  v_amount numeric(14,2);
  v_offset integer;
  v_next_number integer;
  v_horizon date;
  v_limit date;
  v_due date;
  v_created integer := 0;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not public.has_permission('contract_installments', 'write') then
    raise exception 'Sem permissão para estender parcelas' using errcode = '42501';
  end if;

  select id, status, payment_type, fee_value, first_due_date, start_date, end_date,
         readjustment_index, readjustment_cycle_months
    into v_c
    from public.contracts
   where id = p_contract_id
     for update;
  if not found then
    raise exception 'contrato % não encontrado', p_contract_id using errcode = 'P0002';
  end if;

  if v_c.status = 'encerrado' then
    raise exception 'contrato encerrado: não estende parcelas' using errcode = '55000';
  end if;
  if v_c.payment_type <> 'mensal_recorrente' then
    raise exception 'extensão só vale para contrato mensal_recorrente (este é %)', v_c.payment_type
      using errcode = '55000';
  end if;
  if v_c.first_due_date is null then
    raise exception 'contrato sem first_due_date' using errcode = '55000';
  end if;
  if v_c.end_date is not null and v_c.end_date < current_date then
    raise exception 'contrato com end_date já passado (%): nada a estender', v_c.end_date using errcode = '55000';
  end if;

  select count(*) into v_offset
    from public.contract_installments
   where contract_id = p_contract_id and origin = 'projetada';
  if v_offset = 0 then
    raise exception 'contrato sem parcelas projetadas: gere primeiro com generate_contract_installments'
      using errcode = '55000';
  end if;

  select revenue_type, destination_account, readjustment_factor
    into v_ref
    from public.contract_installments
   where contract_id = p_contract_id and origin = 'projetada' and status <> 'cancelada'
   order by due_date desc, installment_number desc
   limit 1;
  if not found then
    -- todas as projetadas canceladas: herda tipo e conta da última, fator 1
    select revenue_type, destination_account, 1::numeric as readjustment_factor
      into v_ref
      from public.contract_installments
     where contract_id = p_contract_id and origin = 'projetada'
     order by due_date desc, installment_number desc
     limit 1;
  end if;

  v_amount := round(v_c.fee_value, 2);
  v_has_readj := v_c.readjustment_index is not null and btrim(v_c.readjustment_index) <> ''
                 and coalesce(v_c.readjustment_cycle_months, 0) > 0;
  -- último dia do mês que fica 12 meses à frente do mês atual
  v_horizon := (date_trunc('month', current_date::timestamp) + interval '13 months' - interval '1 day')::date;
  v_limit := least(v_horizon, coalesce(v_c.end_date, v_horizon));

  select coalesce(max(installment_number), 0) + 1 into v_next_number
    from public.contract_installments where contract_id = p_contract_id;

  loop
    v_due := (v_c.first_due_date + make_interval(months => v_offset))::date;
    exit when v_due > v_limit;

    -- já existe projetada (qualquer status) nesse vencimento: avança sem inserir
    if exists (select 1 from public.contract_installments
                where contract_id = p_contract_id and origin = 'projetada' and due_date = v_due) then
      v_offset := v_offset + 1;
      continue;
    end if;

    -- 047: exige versão da regra de divisão vigente no mês da 1ª parcela a criar
    if v_created = 0 and not exists (
         select 1 from public.contract_revenue_splits
          where contract_id = p_contract_id
            and valid_from <= date_trunc('month', v_due::timestamp)::date) then
      raise exception 'contrato sem regra de divisão de receita vigente em % (mês da 1ª parcela a criar): grave uma versão com set_contract_splits antes de estender',
        date_trunc('month', v_due::timestamp)::date
        using errcode = '55000';
    end if;

    insert into public.contract_installments (
      contract_id, installment_number, revenue_type, origin, due_date,
      base_amount, readjustment_factor, expected_amount, status,
      is_revision_point, destination_account, created_by
    ) values (
      p_contract_id, v_next_number + v_created, v_ref.revenue_type, 'projetada', v_due,
      v_amount, v_ref.readjustment_factor, round(v_amount * v_ref.readjustment_factor, 2), 'projetada',
      v_has_readj and public.fn_contract_is_revision_point(
        v_c.start_date, v_c.readjustment_cycle_months,
        (v_c.first_due_date + make_interval(months => v_offset - 1))::date, v_due),
      v_ref.destination_account, v_uid
    );

    v_offset := v_offset + 1;
    v_created := v_created + 1;
  end loop;

  return v_created;
end;
$$;
