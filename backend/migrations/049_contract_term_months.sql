-- ============================================================
-- 049_contract_term_months.sql
-- Prazo em meses e intervalo de cobrança no contrato e na proposta, geração
-- do parcelado como recorrente com prazo e encerramento de contrato com
-- aviso prévio de 30 dias.
--
-- REGRA (decisão 2026-10-05): fee_value é o valor de CADA PARCELA; o contrato
-- tem uma quantidade de meses prevista (term_months) e um intervalo de
-- cobrança em meses (billing_interval_months: 1 mensal, 2 bimestral,
-- 3 trimestral, 4, 6 ou 12). O valor global não é gravado: é calculado onde
-- for preciso (fee_value x term_months / billing_interval_months,
-- contratual, e soma das parcelas, com reajuste; nas views da 051).
--
-- O QUE FAZ:
--   1. contracts.term_months e proposals.term_months: integer, aceitam nulo
--      por enquanto (a tela atual não preenche), check > 0.
--      contracts.billing_interval_months e proposals.billing_interval_months:
--      integer not null default 1 (as linhas existentes ficam mensais),
--      check in (1, 2, 3, 4, 6, 12).
--      contracts.termination_notice_date (date) e contracts.termination_reason
--      (text), nulos: gravados pela close_contract.
--   2. Preenche term_months = installments_count nos contratos e propostas
--      'parcelado' que têm installments_count (hoje só há linhas assim no
--      staging). installments_count continua na tabela porque o frontend
--      ainda grava; ganha comentário de "substituído por term_months".
--   3. generate_contract_installments (create or replace com o corpo da 047
--      e blocos "049:"): mensal_recorrente e parcelado geram do mesmo jeito,
--      parcelas de fee_value com vencimento n = first_due_date +
--      n x billing_interval_months meses (sempre a partir do primeiro), sem
--      passar do end_date. Com prazo: term_months / intervalo parcelas, todas
--      de uma vez; term_months que não é múltiplo do intervalo é recusado
--      (22023). Sem prazo: 12 / intervalo parcelas (um ano). parcela_unica:
--      1. parcelado sem term_months é recusado (22023).
--      UNIFICAÇÃO EM FASES: 'parcelado' continua aceito nos checks de
--      contracts e proposals até o frontend deixar de usá-lo; uma migration
--      posterior migra os dados e tira 'parcelado' dos checks.
--   4. extend_recurring_installments (create or replace com o corpo da 047 e
--      blocos "049:"): vale para mensal e parcelado; o passo é o intervalo;
--      contrato com prazo não passa de term_months / intervalo parcelas
--      projetadas; term_months que não é múltiplo do intervalo é recusado
--      (22023, mesma mensagem da geração; cobre prazo editado depois de
--      gerar); o horizonte (12 meses à frente do mês atual) e o pulo de
--      vencimento que já tem projetada continuam; o ponto de revisão usa o
--      vencimento anterior pelo mesmo passo.
--   5. close_contract(p_contract_id, p_notice_date, p_reason default null)
--      devolve (cancelled_installments, open_avulsa_installments). AVISO
--      PRÉVIO: a data final é sempre p_notice_date + 30 dias corridos,
--      calculada aqui e nunca recebida de fora. Exige escrita em contratos
--      (crm) E em parcelas (financeiro); recusa contrato já encerrado
--      (55000), data do aviso nula (22004), data do aviso futura
--      (p_notice_date > current_date, 22023) ou data final anterior ao
--      início (22023), e recusa (55000) se houver parcela emitida ou
--      recebida com vencimento depois da data final, informando quantas.
--      Cancela só as parcelas origin = 'projetada' ainda 'projetada' com
--      vencimento depois da data final; as avulsas ficam e são contadas.
--      Grava termination_notice_date, termination_reason (como
--      nullif(btrim(p_reason), ''): sem espaços nas pontas, vazio vira nulo),
--      end_date e status 'encerrado'. Depois disso geração e extensão já
--      recusam o contrato (046).
--   6. trg_contracts_guard_close, para quem chama pela API (auth.uid() não
--      nulo), recusa (42501): a) mudar contracts.status para 'encerrado'
--      fora da close_contract; b) REABRIR: mudar de 'encerrado' para
--      qualquer outro status. close_contract marca a transação com
--      set_config('app.closing_contract', <id do contrato>, true) logo antes
--      do update, e o trigger só deixa passar o contrato marcado. Migration
--      e service role (auth.uid() nulo) não são barrados, como no trigger de
--      system_role da 043. Não cobre INSERT já com 'encerrado' (não pedido).
--      Nenhuma tela grava em contracts direto (conferido no frontend em
--      2026-10-05).
--   create or replace mantém dono e privilégios de generate e extend.
--
-- NÃO FAZ: não muda close_deal (cópia de term_months, billing_interval_months
-- e first_due_date fica na 050), não tira 'parcelado' dos checks, não cria
-- views (051).
--
-- ROLLBACK (na ordem):
--   drop trigger if exists trg_contracts_guard_close on public.contracts;
--   drop function if exists public.fn_contracts_guard_close();
--   drop function if exists public.close_contract(uuid, date, text);
--   -- reaplicar as seções 5a e 5b da 047 (generate e extend, create or replace)
--   comment on column public.contracts.installments_count is null;
--   comment on column public.proposals.installments_count is null;
--   alter table public.contracts drop column if exists termination_reason;
--   alter table public.contracts drop column if exists termination_notice_date;
--   alter table public.proposals drop column if exists billing_interval_months;
--   alter table public.contracts drop column if exists billing_interval_months;
--   alter table public.proposals drop column if exists term_months;
--   alter table public.contracts drop column if exists term_months;
--   (o preenchimento do item 2 some junto com a coluna)
-- ============================================================

-- 1. Prazo em meses
alter table public.contracts add column term_months integer
  constraint contracts_term_months_positive check (term_months is null or term_months > 0);
alter table public.proposals add column term_months integer
  constraint proposals_term_months_positive check (term_months is null or term_months > 0);

comment on column public.contracts.term_months is
  'Quantidade de meses prevista. fee_value é o valor de cada parcela; valor global = fee_value x term_months / billing_interval_months (não gravado). Desde a 049.';
comment on column public.proposals.term_months is
  'Quantidade de meses prevista. value é o valor de cada parcela; valor global = value x term_months / billing_interval_months (não gravado). Desde a 049.';

-- 1b. Intervalo de cobrança em meses (linhas existentes ficam mensais)
alter table public.contracts add column billing_interval_months integer not null default 1
  constraint contracts_billing_interval_months_valid check (billing_interval_months in (1, 2, 3, 4, 6, 12));
alter table public.proposals add column billing_interval_months integer not null default 1
  constraint proposals_billing_interval_months_valid check (billing_interval_months in (1, 2, 3, 4, 6, 12));

comment on column public.contracts.billing_interval_months is
  'Intervalo de cobrança em meses (1 mensal, 2 bimestral, 3 trimestral, 4, 6, 12). Vencimento n = first_due_date + n x intervalo. Desde a 049.';
comment on column public.proposals.billing_interval_months is
  'Intervalo de cobrança em meses (1 mensal, 2 bimestral, 3 trimestral, 4, 6, 12). Desde a 049.';

-- 1c. Encerramento (gravados pela close_contract)
alter table public.contracts add column termination_notice_date date;
alter table public.contracts add column termination_reason text;

comment on column public.contracts.termination_notice_date is
  'Data do aviso prévio de encerramento; end_date = esta data + 30 dias. Gravada pela close_contract. Desde a 049.';
comment on column public.contracts.termination_reason is
  'Motivo do encerramento, informado na close_contract. Desde a 049.';

-- 2. Preenche a partir do installments_count dos parcelados
update public.contracts set term_months = installments_count
 where payment_type = 'parcelado' and installments_count is not null and term_months is null;
update public.proposals set term_months = installments_count
 where payment_type = 'parcelado' and installments_count is not null and term_months is null;

comment on column public.contracts.installments_count is
  'Substituído por term_months (049). Mantido enquanto o frontend grava.';
comment on column public.proposals.installments_count is
  'Substituído por term_months (049). Mantido enquanto o frontend grava.';

-- 3. generate_contract_installments: corpo da 047 + blocos 049
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
         c.readjustment_index, c.readjustment_cycle_months, st.default_revenue_type,
         c.term_months, c.billing_interval_months  -- 049
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
  -- 049: parcelado = recorrente com prazo (fee_value é o valor de cada parcela); sem term_months é recusado
  if v_c.payment_type = 'parcelado' and v_c.term_months is null then
    raise exception 'contrato parcelado sem term_months: informe a quantidade de meses prevista'
      using errcode = '22023';
  end if;
  -- 049: o prazo precisa fechar um número inteiro de intervalos
  if v_c.payment_type <> 'parcela_unica' and v_c.term_months is not null
     and v_c.term_months % v_c.billing_interval_months <> 0 then
    raise exception 'term_months (%) não é múltiplo do intervalo de cobrança (% meses)',
      v_c.term_months, v_c.billing_interval_months
      using errcode = '22023';
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
  -- 049: com prazo, gera term_months / intervalo parcelas de uma vez; sem prazo, um ano (12 / intervalo)
  v_total := case when v_c.payment_type = 'parcela_unica' then 1
                  when v_c.term_months is not null then v_c.term_months / v_c.billing_interval_months
                  else 12 / v_c.billing_interval_months end;

  -- avulsas já lançadas ocupam números: continua depois delas
  select coalesce(max(installment_number), 0) + 1 into v_next_number
    from public.contract_installments where contract_id = p_contract_id;

  for n in 0 .. v_total - 1 loop
    -- 049: vencimento n = first_due_date + n x intervalo, sempre a partir do primeiro
    v_due := (v_c.first_due_date + make_interval(months => n * v_c.billing_interval_months))::date;
    -- 049: o end_date limita mensal e parcelado
    exit when v_c.payment_type <> 'parcela_unica' and v_c.end_date is not null and v_due > v_c.end_date;

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

-- 4. extend_recurring_installments: corpo da 047 + blocos 049
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
         readjustment_index, readjustment_cycle_months,
         term_months, billing_interval_months  -- 049
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
  -- 049: parcelado também é mensal
  if v_c.payment_type not in ('mensal_recorrente', 'parcelado') then
    raise exception 'extensão só vale para contrato mensal_recorrente ou parcelado (este é %)', v_c.payment_type
      using errcode = '55000';
  end if;
  -- 049: o prazo precisa fechar um número inteiro de intervalos (mesma regra da geração)
  if v_c.term_months is not null and v_c.term_months % v_c.billing_interval_months <> 0 then
    raise exception 'term_months (%) não é múltiplo do intervalo de cobrança (% meses)',
      v_c.term_months, v_c.billing_interval_months
      using errcode = '22023';
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
    -- 049: o passo é o intervalo de cobrança
    v_due := (v_c.first_due_date + make_interval(months => v_offset * v_c.billing_interval_months))::date;
    exit when v_due > v_limit;
    -- 049: contrato com prazo não passa de term_months / intervalo parcelas projetadas
    exit when v_c.term_months is not null and v_offset >= v_c.term_months / v_c.billing_interval_months;

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
        -- 049: vencimento anterior pelo mesmo passo
        (v_c.first_due_date + make_interval(months => (v_offset - 1) * v_c.billing_interval_months))::date, v_due),
      v_ref.destination_account, v_uid
    );

    v_offset := v_offset + 1;
    v_created := v_created + 1;
  end loop;

  return v_created;
end;
$$;

-- 5. close_contract
create function public.close_contract(p_contract_id uuid, p_notice_date date, p_reason text default null)
returns table (cancelled_installments integer, open_avulsa_installments integer)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_c record;
  v_end_date date;
  v_locked integer;
  v_cancelled integer;
  v_open integer;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not (public.has_permission('contracts', 'write')
          and public.has_permission('contract_installments', 'write')) then
    raise exception 'Sem permissão para encerrar contrato (exige escrita em contratos e em parcelas)'
      using errcode = '42501';
  end if;
  if p_contract_id is null then
    raise exception 'p_contract_id é obrigatório' using errcode = '22004';
  end if;
  if p_notice_date is null then
    raise exception 'p_notice_date é obrigatório' using errcode = '22004';
  end if;
  if p_notice_date > current_date then
    raise exception 'p_notice_date (%) é futura: o aviso só pode ser registrado depois de dado', p_notice_date
      using errcode = '22023';
  end if;
  -- aviso prévio: a data final é sempre o aviso + 30 dias corridos, nunca recebida de fora
  v_end_date := p_notice_date + 30;

  select id, status, start_date into v_c
    from public.contracts
   where id = p_contract_id
     for update;
  if not found then
    raise exception 'contrato % não encontrado', p_contract_id using errcode = 'P0002';
  end if;
  if v_c.status = 'encerrado' then
    raise exception 'contrato já está encerrado' using errcode = '55000';
  end if;
  if v_end_date < v_c.start_date then
    raise exception 'data final (% = aviso + 30 dias) é anterior ao início do contrato (%)', v_end_date, v_c.start_date
      using errcode = '22023';
  end if;

  -- parcela já emitida ou recebida depois da data final não pode ser cancelada
  select count(*) into v_locked
    from public.contract_installments
   where contract_id = p_contract_id
     and status in ('emitida', 'recebida')
     and due_date > v_end_date;
  if v_locked > 0 then
    raise exception 'há % parcela(s) emitida(s) ou recebida(s) com vencimento depois de % (aviso + 30 dias): não é possível encerrar com esse aviso',
      v_locked, v_end_date
      using errcode = '55000';
  end if;

  -- cancela só as projetadas pela geração; as avulsas ficam e são contadas
  update public.contract_installments
     set status = 'cancelada'
   where contract_id = p_contract_id
     and origin = 'projetada'
     and status = 'projetada'
     and due_date > v_end_date;
  get diagnostics v_cancelled = row_count;

  select count(*) into v_open
    from public.contract_installments
   where contract_id = p_contract_id
     and origin = 'avulsa'
     and status = 'projetada'
     and due_date > v_end_date;

  -- libera o trg_contracts_guard_close só para este contrato, só nesta transação
  perform set_config('app.closing_contract', p_contract_id::text, true);
  update public.contracts
     set status = 'encerrado',
         end_date = v_end_date,
         termination_notice_date = p_notice_date,
         termination_reason = nullif(btrim(p_reason), '')
   where id = p_contract_id;
  perform set_config('app.closing_contract', '', true);

  return query select v_cancelled, v_open;
end;
$$;

revoke execute on function public.close_contract(uuid, date, text) from public, anon;
grant execute on function public.close_contract(uuid, date, text) to authenticated;

-- 6. Encerrar só pela close_contract e não reabrir (para quem chama pela API)
-- Mesmo padrão do trigger de system_role da 043: com auth.uid() nulo
-- (migration, service role) não barra. Revoke de EXECUTE na função de
-- trigger como na 043 (não afeta o disparo).
create function public.fn_contracts_guard_close()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if auth.uid() is null then
    return new;
  end if;

  if new.status = 'encerrado' and old.status is distinct from 'encerrado'
     and coalesce(current_setting('app.closing_contract', true), '') <> new.id::text then
    raise exception 'contrato só pode ser encerrado pela função close_contract'
      using errcode = '42501';
  end if;

  -- contrato encerrado não volta a outro status pela API
  if old.status = 'encerrado' and new.status is distinct from 'encerrado' then
    raise exception 'contrato encerrado não pode ser reaberto'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_contracts_guard_close() from public, anon, authenticated;

create trigger trg_contracts_guard_close
  before update of status on public.contracts
  for each row
  execute function public.fn_contracts_guard_close();
