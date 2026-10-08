-- ============================================================
-- 053_reimbursement_approved_amount.sql
-- Valor aprovado por item de reembolso: o master pode aprovar um item por um
-- valor diferente do pedido, com uma observação opcional, enquanto o
-- relatório está em 'enviado'.
--
-- O QUE FAZ:
--   1. public.reimbursement_items.approved_amount: numeric, aceita nulo, sem
--      default. Nulo = aprovado pelo valor pedido (total_amount). Pode ser
--      maior, menor ou zero. Coluna nula sem default: o ALTER só muda o
--      catálogo, não reescreve a tabela. Nenhuma linha existente é preenchida.
--   2. public.reimbursement_items.approval_note: text, aceita nulo, sem
--      default. Observação opcional de quem aprova; nunca obrigatória.
--   3. trg_reimbursement_items_guard_approved_amount (BEFORE INSERT OR UPDATE
--      em reimbursement_items, por linha, em todo UPDATE do item; função
--      public.fn_reimbursement_items_guard_approved_amount, security
--      definer, search_path vazio). Mesmo padrão do
--      fn_reimbursement_reports_guard_approval (052):
--        - migration e service role (auth.uid() nulo) sempre passam;
--        - INSERT pela API: approved_amount e approval_note têm que vir nulos;
--          senão recusa com 42501 (o item nasce sem valor aprovado);
--        - UPDATE feito pelo master num item cujo relatório (OLD.report_id)
--          está em 'enviado' e não é dele: só approved_amount e approval_note
--          podem mudar; qualquer outra coluna diferente entre OLD e NEW é
--          recusada com 42501 (comparação por to_jsonb, como na 052). Fora
--          desse caso o bloco não se aplica, e quem decide é a RLS
--          (reimbursement_items_update: dono e rascunho);
--        - UPDATE em que nenhuma das duas colunas mudou de valor: passa;
--        - senão, só o master (is_master()) altera, só com o relatório do
--          item (report_id) em 'enviado' e só se o relatório não for dele
--          (profile_id <> auth.uid(), como na 052); fora disso recusa com 42501.
--      security definer: lê status e profile_id em reimbursement_reports sem
--      depender da RLS de quem grava. EXECUTE revogado de public, anon e
--      authenticated (não afeta o disparo).
--   4. Policy nova e separada reimbursement_items_approve_amount (FOR UPDATE,
--      authenticated): USING e WITH CHECK is_master(), relatório do item em
--      'enviado' e relatório que não é do próprio master. Redundante com o
--      gatilho, mesmo padrão da 052 para reimbursement_reports_approve. A
--      reimbursement_items_update (052, dono e rascunho) não muda; as policies
--      FOR UPDATE se somam (permissivas). A policy não limita colunas: a
--      restrição de colunas é do gatilho do item 3.
--   5. Check reimbursement_items_approved_amount_nonneg: approved_amount nulo
--      ou >= 0. A coluna é nova e nula em todas as linhas, então a validação
--      do check só lê a tabela e não falha.
--
-- REGRA DO VALOR:
--   - approved_amount nulo ou igual a total_amount = aprovação integral do item;
--   - valor total do reembolso a pagar = soma de
--     coalesce(approved_amount, total_amount) dos itens do relatório;
--   - essa soma ainda não existe no banco (nem view nem função).
--
-- NENHUM UPDATE, INSERT OU DELETE em linhas existentes: só duas colunas
-- novas, um check, uma função, um gatilho e uma policy.
--
-- NÃO FAZ:
--   - função ou view que soma o total aprovado (fica para a migration que liga
--     reembolso a pagamento);
--   - frontend (tela de aprovação com o valor aprovado e a observação por item).
--
-- ROLLBACK (na ordem; apaga os valores aprovados e as observações gravados):
--   drop policy if exists reimbursement_items_approve_amount on public.reimbursement_items;
--   drop trigger if exists trg_reimbursement_items_guard_approved_amount on public.reimbursement_items;
--   drop function if exists public.fn_reimbursement_items_guard_approved_amount();
--   alter table public.reimbursement_items drop constraint if exists reimbursement_items_approved_amount_nonneg;
--   alter table public.reimbursement_items drop column if exists approval_note;
--   alter table public.reimbursement_items drop column if exists approved_amount;
-- ============================================================

-- 1 e 2. Colunas novas
alter table public.reimbursement_items
  add column approved_amount numeric,
  add column approval_note text;

alter table public.reimbursement_items
  add constraint reimbursement_items_approved_amount_nonneg
  check (approved_amount is null or approved_amount >= 0);

comment on column public.reimbursement_items.approved_amount is
  'Valor aprovado pelo master para o item. Nulo = aprovado pelo valor pedido '
  '(total_amount). A pagar no relatório = soma de coalesce(approved_amount, total_amount) (053).';

comment on column public.reimbursement_items.approval_note is
  'Observação opcional de quem aprova o item (053).';

-- 3. Só o master altera, só com o relatório de outro usuário em 'enviado';
--    o item nasce sem valor aprovado
create function public.fn_reimbursement_items_guard_approved_amount()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_status text;
  v_owner uuid;
begin
  if auth.uid() is null then
    return new;
  end if;

  if tg_op = 'INSERT' then
    if new.approved_amount is not null or new.approval_note is not null then
      raise exception 'approved_amount e approval_note não podem vir preenchidos na criação do item: só o master os grava, na aprovação'
        using errcode = '42501';
    end if;
    return new;
  end if;

  -- master aprovando item de outro usuário em 'enviado': só as duas colunas mudam
  select r.status, r.profile_id into v_status, v_owner
  from public.reimbursement_reports r
  where r.id = old.report_id;

  if public.is_master() and v_status = 'enviado' and v_owner is distinct from auth.uid() then
    if (to_jsonb(new) - array['approved_amount', 'approval_note', 'updated_at'])
       is distinct from
       (to_jsonb(old) - array['approved_amount', 'approval_note', 'updated_at']) then
      raise exception 'na aprovação do item só podem mudar approved_amount e approval_note'
        using errcode = '42501';
    end if;
  end if;

  if new.approved_amount is not distinct from old.approved_amount
     and new.approval_note is not distinct from old.approval_note then
    return new;
  end if;

  if not public.is_master() then
    raise exception 'approved_amount e approval_note só podem ser alterados pelo master'
      using errcode = '42501';
  end if;

  select r.status, r.profile_id into v_status, v_owner
  from public.reimbursement_reports r
  where r.id = new.report_id;

  if v_owner = auth.uid() then
    raise exception 'o master não ajusta approved_amount nem approval_note de itens do próprio relatório'
      using errcode = '42501';
  end if;

  if v_status is distinct from 'enviado' then
    raise exception 'approved_amount e approval_note só podem ser alterados com o relatório em ''enviado'' (está em %)',
      coalesce(v_status, 'relatório inexistente')
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_reimbursement_items_guard_approved_amount() from public, anon, authenticated;

create trigger trg_reimbursement_items_guard_approved_amount
  before insert or update on public.reimbursement_items
  for each row
  execute function public.fn_reimbursement_items_guard_approved_amount();

-- 4. Master grava o valor aprovado com o relatório de outro usuário em 'enviado'.
--    A RLS libera o UPDATE da linha; quem decide o conteúdo (o que pode mudar
--    e com que valor) é o gatilho do item 3.
create policy reimbursement_items_approve_amount on public.reimbursement_items
  for update to authenticated
  using (public.is_master() and exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id and r.status = 'enviado'
      and r.profile_id <> auth.uid()
  ))
  with check (public.is_master() and exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id and r.status = 'enviado'
      and r.profile_id <> auth.uid()
  ));
