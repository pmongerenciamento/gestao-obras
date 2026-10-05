-- ============================================================
-- 046_installment_functions.sql
-- Funções do calendário de parcelas (045): geração, extensão do
-- horizonte, reajuste e confirmação de recebimento; vínculo da
-- conciliação bancária com as parcelas.
--
-- O QUE FAZ:
--   1. public.contracts.first_due_date (date, nulo, sem padrão): 1º
--      vencimento do contrato, base de todo o calendário. close_deal NÃO
--      muda aqui (fica para uma migration própria): até lá, preencher à mão.
--   2. public.bank_transactions:
--      - FK matched_contract_installment_id -> contract_installments(id),
--        sem ON DELETE (padrão: bloqueia apagar parcela conciliada). É a
--        FK que a 038 deixou anotada para "quando contract_installments
--        existir"; o comentário da coluna no banco passa a dizer isso.
--      - check de exclusividade: não pode ter despesa e parcela juntas.
--      - check de direção: parcela só em crédito, despesa só em débito.
--      - índice único parcial em matched_contract_installment_id (uma
--        parcela só pode ser quitada por uma transação).
--   3. public.fn_contract_is_revision_point(start, ciclo, venc_anterior,
--      venc): auxiliar interna (SQL, immutable, sem acesso a tabela). True
--      se algum aniversário start + k*ciclo meses (k >= 1) cai em
--      (venc_anterior, venc]; com venc_anterior nulo, em (-inf, venc].
--      Sem EXECUTE para ninguém da API.
--   4. public.generate_contract_installments(contrato, tipo, conta):
--      parcela_unica = 1 parcela no first_due_date; mensal_recorrente = 12
--      parcelas (ou até end_date), valor mensal = fee_value; parcelado é
--      RECUSADO até confirmarmos o sentido de fee_value. Vencimento n =
--      first_due_date + n meses, sempre a partir do 1º (nunca em cadeia):
--      31/01 -> 28/02 -> 31/03, sem "grudar" no dia 28. Recusa contrato
--      'encerrado' ('suspenso' é permitido).
--   5. public.extend_recurring_installments(contrato): completa o mensal
--      até o fim do mês 12 meses à frente do mês atual (ou end_date),
--      herdando o fator de reajuste da última parcela projetada não
--      cancelada. Pula qualquer vencimento que já tenha parcela projetada
--      (origin = 'projetada', qualquer status). Recusa contrato
--      'encerrado'. Idempotente.
--   6. public.apply_readjustment(parcela_revisão, pct, mês_ref, índice):
--      grava contract_readjustments e recalcula SÓ as parcelas projetadas
--      (origin e status) do contrato com vencimento a partir da revisão.
--      Recusa se já existe reajuste aplicado numa parcela de revisão
--      posterior do mesmo contrato (reajustes em ordem cronológica).
--   7. public.confirm_installment_receipt_from_bank(transação, parcela):
--      casa um crédito do Inter com uma parcela em conta conciliada pela
--      API. Só quando chamada (nunca automática).
--   8. public.confirm_installment_receipt_manual(parcela, data, valor):
--      recebimento das parcelas em conta NÃO conciliada pela API (PF).
--
-- Todas as funções 4-8: security definer, search_path = '', exigem
-- auth.uid() não nulo e has_permission(); revoke de public e anon, grant
-- só para authenticated (padrão da 041). Erros de estado usam 55000
-- (object_not_in_prerequisite_state); parcelado usa 0A000.
--
-- NÃO FAZ: close_deal copiando first_due_date (migration própria); views
-- do DRE (047); matching automático de créditos (backend Python).
--
-- ROLLBACK (na ordem; NÃO desfaz parcelas, reajustes ou conciliações já
-- gravados pelas funções):
--   drop function if exists public.confirm_installment_receipt_manual(uuid, date, numeric);
--   drop function if exists public.confirm_installment_receipt_from_bank(uuid, uuid);
--   drop function if exists public.apply_readjustment(uuid, numeric, date, text);
--   drop function if exists public.extend_recurring_installments(uuid);
--   drop function if exists public.generate_contract_installments(uuid, text, text);
--   drop function if exists public.fn_contract_is_revision_point(date, integer, date, date);
--   drop index if exists public.uq_bank_transactions_matched_installment;
--   alter table public.bank_transactions drop constraint if exists bank_transactions_match_direction_check;
--   alter table public.bank_transactions drop constraint if exists bank_transactions_single_match_check;
--   alter table public.bank_transactions drop constraint if exists bank_transactions_matched_contract_installment_id_fkey;
--   comment on column public.bank_transactions.matched_contract_installment_id is null;
--   alter table public.contracts drop column if exists first_due_date;
-- ============================================================

-- 1. contracts.first_due_date
alter table public.contracts add column first_due_date date;

-- 2. bank_transactions <-> contract_installments
alter table public.bank_transactions
  add constraint bank_transactions_matched_contract_installment_id_fkey
  foreign key (matched_contract_installment_id) references public.contract_installments(id);

alter table public.bank_transactions
  add constraint bank_transactions_single_match_check
  check (matched_expense_id is null or matched_contract_installment_id is null);

alter table public.bank_transactions
  add constraint bank_transactions_match_direction_check
  check ((matched_contract_installment_id is null or type = 'credito')
     and (matched_expense_id is null or type = 'debito'));

create unique index uq_bank_transactions_matched_installment
  on public.bank_transactions (matched_contract_installment_id)
  where matched_contract_installment_id is not null;

comment on column public.bank_transactions.matched_contract_installment_id is
  'Parcela de receita (contract_installments) quitada por este crédito. FK desde a 046; '
  'só em transação de crédito, exclusiva com matched_expense_id, no máximo uma transação por parcela.';

-- 3. Auxiliar: ponto de revisão
create function public.fn_contract_is_revision_point(
  p_start date, p_cycle integer, p_prev_due date, p_due date)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select coalesce(p_cycle, 0) > 0
     and p_due >= p_start
     and exists (
       select 1
       from generate_series(
              1,
              -- age() com ::timestamp: com date puro o Postgres escolhe a
              -- versão timestamptz (STABLE, depende do fuso), como na 045
              ((extract(year from age(p_due::timestamp, p_start::timestamp)) * 12
                + extract(month from age(p_due::timestamp, p_start::timestamp)))::integer
               / nullif(p_cycle, 0)) + 1
            ) as k
       where (p_start + make_interval(months => k * p_cycle))::date <= p_due
         and (p_prev_due is null
              or (p_start + make_interval(months => k * p_cycle))::date > p_prev_due)
     );
$$;

revoke execute on function public.fn_contract_is_revision_point(date, integer, date, date)
  from public, anon, authenticated;

-- 4. generate_contract_installments
create function public.generate_contract_installments(
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

revoke execute on function public.generate_contract_installments(uuid, text, text) from public, anon;
grant execute on function public.generate_contract_installments(uuid, text, text) to authenticated;

-- 5. extend_recurring_installments
-- Posição na sequência projetada = quantas parcelas origin = 'projetada' o
-- contrato já tem (inclusive canceladas): a próxima é first_due_date +
-- essa quantidade de meses. Tipo, conta e fator vêm da última projetada
-- não cancelada (avulsas, como reembolso, não entram).
create function public.extend_recurring_installments(p_contract_id uuid)
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

revoke execute on function public.extend_recurring_installments(uuid) from public, anon;
grant execute on function public.extend_recurring_installments(uuid) to authenticated;

-- 6. apply_readjustment
-- p_percentage em pontos percentuais: 4.53 = 4,53%. Até 4 casas
-- (contract_readjustments.percentage é numeric(8,4)).
create function public.apply_readjustment(
  p_revision_installment_id uuid,
  p_percentage numeric,
  p_reference_month date,
  p_index_code text default 'INCC')
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_rev record;
  v_before numeric;
  v_after numeric;
  v_rows integer;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not (public.has_permission('contract_installments', 'write')
          and public.has_permission('contract_readjustments', 'write')) then
    raise exception 'Sem permissão para aplicar reajuste' using errcode = '42501';
  end if;

  if p_percentage is null or p_percentage <> round(p_percentage, 4) then
    raise exception 'p_percentage obrigatório, com até 4 casas decimais (4.53 = 4,53%%)' using errcode = '22023';
  end if;
  if p_reference_month is null or extract(day from p_reference_month) <> 1 then
    raise exception 'p_reference_month obrigatório e no dia 1 do mês' using errcode = '22023';
  end if;
  if p_index_code is null or btrim(p_index_code) = '' then
    raise exception 'p_index_code obrigatório' using errcode = '22023';
  end if;

  select id, contract_id, due_date, status, is_revision_point, readjustment_factor
    into v_rev
    from public.contract_installments
   where id = p_revision_installment_id
     for update;
  if not found then
    raise exception 'parcela % não encontrada', p_revision_installment_id using errcode = 'P0002';
  end if;

  -- serializa com geração/extensão do mesmo contrato
  perform 1 from public.contracts where id = v_rev.contract_id for update;

  if not v_rev.is_revision_point then
    raise exception 'a parcela não é ponto de revisão (is_revision_point = false)' using errcode = '55000';
  end if;
  if v_rev.status <> 'projetada' then
    raise exception 'a parcela de revisão está %, só projetada pode ser reajustada', v_rev.status using errcode = '55000';
  end if;
  if exists (select 1 from public.contract_readjustments where revision_installment_id = v_rev.id) then
    raise exception 'reajuste já aplicado nesta parcela de revisão' using errcode = '23505';
  end if;
  -- reajustes em ordem cronológica: não aplica um anterior depois de um posterior
  if exists (select 1
               from public.contract_readjustments r
               join public.contract_installments i on i.id = r.revision_installment_id
              where r.contract_id = v_rev.contract_id
                and i.due_date > v_rev.due_date) then
    raise exception 'já existe reajuste aplicado numa parcela de revisão posterior deste contrato: os reajustes são aplicados em ordem cronológica'
      using errcode = '55000';
  end if;

  v_before := v_rev.readjustment_factor;
  v_after := round(v_before * (1 + p_percentage / 100), 8);
  if v_after <= 0 then
    raise exception 'fator resultante deve ser maior que zero (veio %)', v_after using errcode = '22023';
  end if;

  insert into public.contract_readjustments (
    contract_id, revision_installment_id, index_code, reference_month,
    percentage, factor_before, factor_after, applied_by
  ) values (
    v_rev.contract_id, v_rev.id, btrim(p_index_code), p_reference_month,
    p_percentage, v_before, v_after, v_uid
  );

  update public.contract_installments
     set readjustment_factor = v_after,
         expected_amount = round(base_amount * v_after, 2)
   where contract_id = v_rev.contract_id
     and origin = 'projetada'
     and status = 'projetada'
     and due_date >= v_rev.due_date;
  get diagnostics v_rows = row_count;

  return v_rows;
end;
$$;

revoke execute on function public.apply_readjustment(uuid, numeric, date, text) from public, anon;
grant execute on function public.apply_readjustment(uuid, numeric, date, text) to authenticated;

-- 7. confirm_installment_receipt_from_bank
-- Ordem de trava fixa (transação, depois parcela) para não dar deadlock
-- entre duas confirmações concorrentes.
create function public.confirm_installment_receipt_from_bank(
  p_bank_transaction_id uuid,
  p_installment_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_tx record;
  v_inst record;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not (public.has_permission('contract_installments', 'write')
          and public.has_permission('expenses', 'write')) then
    raise exception 'Sem permissão para conciliar recebimento' using errcode = '42501';
  end if;

  select id, type, value, transaction_date, reconciliation_status,
         matched_expense_id, matched_contract_installment_id
    into v_tx
    from public.bank_transactions
   where id = p_bank_transaction_id
     for update;
  if not found then
    raise exception 'transação % não encontrada', p_bank_transaction_id using errcode = 'P0002';
  end if;
  if v_tx.type <> 'credito' then
    raise exception 'só transação de crédito pode quitar parcela (esta é %)', v_tx.type using errcode = '22023';
  end if;
  if v_tx.reconciliation_status not in ('pendente', 'sugerido') then
    raise exception 'transação já está % (só pendente ou sugerido)', v_tx.reconciliation_status using errcode = '55000';
  end if;
  if v_tx.matched_expense_id is not null or v_tx.matched_contract_installment_id is not null then
    raise exception 'transação já vinculada a despesa ou parcela' using errcode = '55000';
  end if;
  if v_tx.value is null or v_tx.value <= 0 then
    raise exception 'transação com valor não positivo' using errcode = '22023';
  end if;

  select i.id, i.status, ba.reconciled_via_bank_api
    into v_inst
    from public.contract_installments i
    join public.bank_accounts ba on ba.code = i.destination_account
   where i.id = p_installment_id
     for update of i;
  if not found then
    raise exception 'parcela % não encontrada', p_installment_id using errcode = 'P0002';
  end if;
  if not v_inst.reconciled_via_bank_api then
    raise exception 'parcela em conta não conciliada pela API: use confirm_installment_receipt_manual'
      using errcode = '55000';
  end if;
  if v_inst.status in ('recebida', 'cancelada') then
    raise exception 'parcela já está %', v_inst.status using errcode = '55000';
  end if;

  update public.contract_installments
     set status = 'recebida',
         received_date = v_tx.transaction_date,
         received_amount = v_tx.value
   where id = v_inst.id;

  update public.bank_transactions
     set reconciliation_status = 'conciliado',
         matched_contract_installment_id = v_inst.id,
         reconciled_by = v_uid,
         reconciled_at = now()
   where id = v_tx.id;
end;
$$;

revoke execute on function public.confirm_installment_receipt_from_bank(uuid, uuid) from public, anon;
grant execute on function public.confirm_installment_receipt_from_bank(uuid, uuid) to authenticated;

-- 8. confirm_installment_receipt_manual (contas não conciliadas pela API: PF)
create function public.confirm_installment_receipt_manual(
  p_installment_id uuid,
  p_received_date date,
  p_received_amount numeric)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_inst record;
begin
  if v_uid is null then
    raise exception 'sessão sem usuário (auth.uid() nulo)' using errcode = '42501';
  end if;
  if not public.has_permission('contract_installments', 'write') then
    raise exception 'Sem permissão para confirmar recebimento' using errcode = '42501';
  end if;
  if p_received_date is null then
    raise exception 'p_received_date obrigatório' using errcode = '22023';
  end if;
  if p_received_amount is null or p_received_amount <= 0 then
    raise exception 'p_received_amount deve ser maior que zero' using errcode = '22023';
  end if;

  select i.id, i.status, ba.reconciled_via_bank_api
    into v_inst
    from public.contract_installments i
    join public.bank_accounts ba on ba.code = i.destination_account
   where i.id = p_installment_id
     for update of i;
  if not found then
    raise exception 'parcela % não encontrada', p_installment_id using errcode = 'P0002';
  end if;
  if v_inst.reconciled_via_bank_api then
    raise exception 'parcela em conta conciliada pela API: o recebimento vem do extrato (confirm_installment_receipt_from_bank)'
      using errcode = '55000';
  end if;
  if v_inst.status in ('recebida', 'cancelada') then
    raise exception 'parcela já está %', v_inst.status using errcode = '55000';
  end if;

  update public.contract_installments
     set status = 'recebida',
         received_date = p_received_date,
         received_amount = p_received_amount
   where id = v_inst.id;
end;
$$;

revoke execute on function public.confirm_installment_receipt_manual(uuid, date, numeric) from public, anon;
grant execute on function public.confirm_installment_receipt_manual(uuid, date, numeric) to authenticated;
