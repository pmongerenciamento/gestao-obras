-- ============================================================
-- 052_reembolso_fixes.sql
-- Correções do módulo de Reembolso encontradas na auditoria de 2026-10-07
-- (conferência só leitura em staging e produção, 2026-10-08): DELETE de
-- itens sem limite de status, aprovação pelo master, validação do total do
-- item contra a taxa vigente e coluna do comprovante.
--
-- O QUE FAZ:
--   1. reimbursement_items: a policy única reimbursement_items_via_report
--      (030, "for all") sai e entram quatro policies separadas:
--        - SELECT: dono do relatório, ou has_permission('reimbursement_reports',
--          'read'), ou master (item 2).
--        - INSERT: dono do relatório, relatório em 'rascunho' (igual ao
--          WITH CHECK de hoje).
--        - UPDATE: dono do relatório, relatório em 'rascunho', antes e depois
--          (USING e WITH CHECK). Hoje o USING aceita dono ou financeiro em
--          qualquer status; só o WITH CHECK exigia dono e rascunho.
--        - DELETE: dono do relatório E relatório em 'rascunho'. Hoje dono ou
--          financeiro apagam item em qualquer status, inclusive de relatório
--          aprovado (o WITH CHECK não vale para DELETE). Fecha isso.
--      DECISÃO: reimbursement_reports continua sem policy de DELETE, ou seja,
--      fechado para authenticated (o grant existe, mas sem policy a RLS
--      recusa). O app não apaga relatório. Não é lacuna: é o comportamento
--      desejado.
--   2. Leitura pelo master: "or public.is_master()" no SELECT de
--      reimbursement_reports (reimbursement_reports_own) e no SELECT novo de
--      reimbursement_items, para o master ver o que pode aprovar mesmo sem o
--      módulo financeiro.
--   3. Aprovação só pelo master:
--      a. reimbursement_reports_approve (030) passa de
--         has_permission('reimbursement_reports', 'write') para:
--           USING      is_master() e profile_id <> auth.uid() e status = 'enviado'
--           WITH CHECK is_master() e profile_id <> auth.uid() e
--                      status in ('aprovado', 'rejeitado') e
--                      (status = 'rejeitado' ou approved_by = auth.uid())
--         approved_by = auth.uid() é exigido só na aprovação. Na rejeição não
--         é exigido porque o rejectReport() do app hoje não grava esse campo.
--         O financeiro deixa de aprovar e rejeitar. Ninguém aprova ou rejeita
--         o próprio relatório: o master, como dono, só tem o caminho da
--         reimbursement_reports_update_own_draft (032), que só leva a
--         'rascunho' ou 'enviado'.
--      b. trg_reimbursement_reports_guard_approval (BEFORE UPDATE em
--         reimbursement_reports, função public.fn_reimbursement_reports_guard_approval):
--         quando quem altera é master (is_master()), a linha está em 'enviado'
--         (OLD.status) e o relatório não é dele (OLD.profile_id <> auth.uid()),
--         só podem mudar status, approved_by, approved_at e rejection_reason;
--         qualquer outra coluna alterada é recusada (42501). updated_at fica
--         de fora da comparação: é preenchido pelo
--         reimbursement_reports_set_updated_at (033), que dispara antes (os
--         triggers BEFORE disparam em ordem alfabética de nome).
--         Não se aplica ao dono mexendo no próprio relatório (fluxo da 032:
--         rascunho/rejeitado -> rascunho/enviado), nem a quem não é master, nem
--         a migration e service role (auth.uid() nulo => is_master() falso).
--         EXECUTE revogado de public, anon e authenticated (não afeta o disparo).
--   4. trg_reimbursement_items_validate_total (BEFORE INSERT OR UPDATE OF type,
--      expense_date, km_traveled, km_rate, toll_amount, other_amount,
--      total_amount em reimbursement_items, por linha; função
--      public.fn_reimbursement_items_validate_total, security definer, search_path
--      vazio). Confere só a linha que está sendo gravada; um UPDATE que não
--      toca essas colunas (ex.: receipt_path, item 5) não reconfere a linha.
--      Taxa vigente = linha de reimbursement_rate_rules do tipo, com a unidade
--      esperada, e effective_start_date <= expense_date <= effective_end_date
--      (fim nulo = sem fim). Nenhuma taxa vigente ou mais de uma: recusa com
--      mensagem, nunca recalcula. Tolerância de R$ 0,01. Recusa com 23514.
--        - deslocamento_escritorio, visita_cliente, visita_comercial (usa a
--          taxa de visita_cliente, igual ao frontend): unidade 'por_km';
--          km_traveled e km_rate obrigatórios; km_rate tem que bater com a
--          taxa vigente; total_amount tem que bater com
--          km_traveled * taxa vigente + toll_amount.
--        - alimentacao: unidade 'valor_fixo_diario'; total_amount tem que
--          bater com a taxa vigente.
--        - outros: sem taxa; total_amount tem que ser igual a other_amount.
--      Vale para todos, inclusive migration e service role: é regra de dado.
--      security definer: lê reimbursement_rate_rules sem depender da RLS de
--      quem grava. EXECUTE revogado de public, anon e authenticated.
--      LIMITE: mudar uma taxa depois não reconfere itens já gravados.
--   5. reimbursement_items.receipt_path: text, aceita nulo, sem default (o
--      ALTER só muda o catálogo). Caminho do comprovante no Storage.
--      A EXIGÊNCIA do comprovante (ex.: item 'outros' ao enviar o relatório)
--      NÃO entra aqui: fica para a 053, depois que existirem o bucket e o
--      upload no frontend. O bucket privado de comprovantes precisa ser
--      criado à mão no painel do Supabase, em staging e em produção, antes de
--      a coluna ter uso prático. Esta migration não cria bucket.
--   6. Rateio do time Diego/Murillo e fallback da regra padrão:
--      a. allocation_rule nova 'Time Diego/Murillo 100%', com uma fatia de
--         100% para o time 'Diego/Murillo' (time buscado pelo NOME, mesmo
--         padrão da 034).
--      b. public.default_allocation_rule_for_profile (035/041): o time
--         'Diego/Murillo' passa a devolver 'Time Diego/Murillo 100%'. Time sem
--         regra mapeada (nem Carlos, nem Weslley, nem Diego/Murillo) ou perfil
--         sem nenhum time passam a devolver NULL, e não mais
--         'Rateio Sócios 50/50 (Carlos/Weslley)'. O rateio desses itens fica a
--         resolver, como o frontend (createItem) já supunha. Mesmos
--         privilégios da 041: EXECUTE só para authenticated.
--
-- NENHUM UPDATE, INSERT OU DELETE em linhas existentes de reimbursement_items,
-- reimbursement_reports, allocation_rules ou allocation_rule_splits: só
-- policies, triggers, funções, uma coluna nova e uma linha nova em
-- allocation_rules e em allocation_rule_splits (item 6a).
--
-- NÃO FAZ:
--   - frontend: trocar cost_centers por expense_categories nas consultas
--     (lib/api/reimbursements.ts) e a permissão da tela /reembolso/aprovacoes
--     para refletir is_master();
--   - frontend: rejectReport() não grava approved_by; corrigir numa mudança
--     futura no frontend para manter o rastro de quem rejeitou cada relatório;
--   - criação do bucket de Storage dos comprovantes (manual, painel);
--   - trigger de exigência de comprovante (053);
--   - backfill ou limpeza dos itens de teste de staging sem allocation_rule_id.
--
-- ROLLBACK (na ordem; apaga os caminhos de comprovante gravados; o delete da
-- regra nova falha se algum item já apontar para ela em allocation_rule_id,
-- e nesse caso esses itens precisam ser tratados antes):
--   create or replace function public.default_allocation_rule_for_profile(p_profile_id uuid)
--   returns uuid
--   language plpgsql
--   security definer
--   stable
--   set search_path = ''
--   as $$
--   declare
--     v_team_name text;
--     v_rule_id uuid;
--   begin
--     select t.name into v_team_name
--     from public.team_members tm
--     join public.teams t on t.id = tm.team_id
--     where tm.profile_id = p_profile_id
--     limit 1;
--
--     if v_team_name = 'Carlos' then
--       select id into v_rule_id from public.allocation_rules where name = 'Time Carlos 100%';
--     elsif v_team_name = 'Weslley' then
--       select id into v_rule_id from public.allocation_rules where name = 'Time Weslley 100%';
--     else
--       select id into v_rule_id from public.allocation_rules where name = 'Rateio Sócios 50/50 (Carlos/Weslley)';
--     end if;
--
--     return v_rule_id;
--   end;
--   $$;
--   revoke execute on function public.default_allocation_rule_for_profile(uuid) from public, anon;
--   grant execute on function public.default_allocation_rule_for_profile(uuid) to authenticated;
--   delete from public.allocation_rules where name = 'Time Diego/Murillo 100%';  -- a fatia sai junto (on delete cascade, 034)
--   drop trigger if exists trg_reimbursement_items_validate_total on public.reimbursement_items;
--   drop function if exists public.fn_reimbursement_items_validate_total();
--   drop trigger if exists trg_reimbursement_reports_guard_approval on public.reimbursement_reports;
--   drop function if exists public.fn_reimbursement_reports_guard_approval();
--   alter policy reimbursement_reports_approve on public.reimbursement_reports
--     using (has_permission('reimbursement_reports', 'write'))
--     with check (has_permission('reimbursement_reports', 'write'));
--   alter policy reimbursement_reports_own on public.reimbursement_reports
--     using (profile_id = auth.uid() or has_permission('reimbursement_reports', 'read'));
--   drop policy if exists reimbursement_items_delete on public.reimbursement_items;
--   drop policy if exists reimbursement_items_update on public.reimbursement_items;
--   drop policy if exists reimbursement_items_insert on public.reimbursement_items;
--   drop policy if exists reimbursement_items_select on public.reimbursement_items;
--   create policy reimbursement_items_via_report on public.reimbursement_items for all to authenticated
--     using (exists (
--       select 1 from reimbursement_reports r where r.id = reimbursement_items.report_id
--       and (r.profile_id = auth.uid() or has_permission('reimbursement_reports', 'read'))
--     ))
--     with check (exists (
--       select 1 from reimbursement_reports r where r.id = reimbursement_items.report_id
--       and r.profile_id = auth.uid() and r.status = 'rascunho'
--     ));
--   alter table public.reimbursement_items drop column if exists receipt_path;
-- ============================================================

-- 1 e 2. Policies de reimbursement_items (separadas por comando)
drop policy reimbursement_items_via_report on public.reimbursement_items;

create policy reimbursement_items_select on public.reimbursement_items
  for select to authenticated
  using (exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id
      and (r.profile_id = auth.uid()
           or public.has_permission('reimbursement_reports', 'read')
           or public.is_master())
  ));

create policy reimbursement_items_insert on public.reimbursement_items
  for insert to authenticated
  with check (exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id
      and r.profile_id = auth.uid() and r.status = 'rascunho'
  ));

create policy reimbursement_items_update on public.reimbursement_items
  for update to authenticated
  using (exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id
      and r.profile_id = auth.uid() and r.status = 'rascunho'
  ))
  with check (exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id
      and r.profile_id = auth.uid() and r.status = 'rascunho'
  ));

create policy reimbursement_items_delete on public.reimbursement_items
  for delete to authenticated
  using (exists (
    select 1 from public.reimbursement_reports r
    where r.id = reimbursement_items.report_id
      and r.profile_id = auth.uid() and r.status = 'rascunho'
  ));

-- 2. Master lê os relatórios
alter policy reimbursement_reports_own on public.reimbursement_reports
  using (profile_id = auth.uid()
         or public.has_permission('reimbursement_reports', 'read')
         or public.is_master());

-- 3a. Aprovação só pelo master, nunca do próprio relatório, só a partir de 'enviado'
alter policy reimbursement_reports_approve on public.reimbursement_reports
  using (public.is_master() and profile_id <> auth.uid() and status = 'enviado')
  with check (public.is_master() and profile_id <> auth.uid() and status in ('aprovado', 'rejeitado')
              and (status = 'rejeitado' or approved_by = auth.uid()));

-- 3b. Quem aprova só mexe nas colunas da aprovação
create function public.fn_reimbursement_reports_guard_approval()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not (public.is_master()
          and old.status = 'enviado'
          and old.profile_id is distinct from auth.uid()) then
    return new;
  end if;

  if (to_jsonb(new) - array['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])
     is distinct from
     (to_jsonb(old) - array['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at']) then
    raise exception 'na aprovação só podem mudar status, approved_by, approved_at e rejection_reason'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_reimbursement_reports_guard_approval() from public, anon, authenticated;

create trigger trg_reimbursement_reports_guard_approval
  before update on public.reimbursement_reports
  for each row
  execute function public.fn_reimbursement_reports_guard_approval();

-- 4. Total do item conferido contra a taxa vigente na data da despesa
-- Regra de dado: vale para todos, inclusive migration e service role.
create function public.fn_reimbursement_items_validate_total()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_rate_type text;
  v_unit text;
  v_count int;
  v_rate numeric;
begin
  if new.type = 'outros' then
    if new.total_amount is distinct from new.other_amount then
      raise exception 'item "outros": total_amount (%) tem que ser igual a other_amount (%)',
        new.total_amount, new.other_amount
        using errcode = '23514';
    end if;
    return new;
  end if;

  if new.type in ('deslocamento_escritorio', 'visita_cliente', 'visita_comercial') then
    v_rate_type := case when new.type = 'visita_comercial' then 'visita_cliente' else new.type end;
    v_unit := 'por_km';
  elsif new.type = 'alimentacao' then
    v_rate_type := 'alimentacao';
    v_unit := 'valor_fixo_diario';
  else
    -- tipo fora da lista: o check de reimbursement_items.type (030) recusa
    return new;
  end if;

  select count(*), min(r.value)
    into v_count, v_rate
  from public.reimbursement_rate_rules r
  where r.type = v_rate_type
    and r.unit = v_unit
    and r.effective_start_date <= new.expense_date
    and (r.effective_end_date is null or r.effective_end_date >= new.expense_date);

  if v_count = 0 then
    raise exception 'sem taxa vigente de % (%) em %: cadastre a taxa em reimbursement_rate_rules antes de lançar o item',
      v_rate_type, v_unit, new.expense_date
      using errcode = '23514';
  end if;

  if v_count > 1 then
    raise exception 'mais de uma taxa vigente de % (%) em %: corrija as vigências em reimbursement_rate_rules',
      v_rate_type, v_unit, new.expense_date
      using errcode = '23514';
  end if;

  if v_unit = 'por_km' then
    if new.km_traveled is null or new.km_rate is null then
      raise exception 'item de km (%): km_traveled e km_rate são obrigatórios', new.type
        using errcode = '23514';
    end if;

    if abs(new.km_rate - v_rate) > 0.01 then
      raise exception 'item de km (%): km_rate % não bate com a taxa vigente % em %',
        new.type, new.km_rate, v_rate, new.expense_date
        using errcode = '23514';
    end if;

    if abs(new.total_amount - (new.km_traveled * v_rate + new.toll_amount)) > 0.01 then
      raise exception 'item de km (%): total_amount % não bate com km_traveled % x taxa % + pedágio % = %',
        new.type, new.total_amount, new.km_traveled, v_rate, new.toll_amount,
        new.km_traveled * v_rate + new.toll_amount
        using errcode = '23514';
    end if;
  else
    if abs(new.total_amount - v_rate) > 0.01 then
      raise exception 'item de alimentação: total_amount % não bate com a diária vigente % em %',
        new.total_amount, v_rate, new.expense_date
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_reimbursement_items_validate_total() from public, anon, authenticated;

create trigger trg_reimbursement_items_validate_total
  before insert or update of type, expense_date, km_traveled, km_rate, toll_amount, other_amount, total_amount
  on public.reimbursement_items
  for each row
  execute function public.fn_reimbursement_items_validate_total();

-- 5. Caminho do comprovante (a exigência fica para a 053)
alter table public.reimbursement_items
  add column receipt_path text;

comment on column public.reimbursement_items.receipt_path is
  'Caminho do comprovante no bucket privado do Storage (bucket criado à mão no '
  'painel). Ainda não exigido: a exigência entra na 053, junto com o upload no frontend.';

-- 6a. Regra do time Diego/Murillo (time buscado pelo nome, padrão da 034)
insert into public.allocation_rules (name) values ('Time Diego/Murillo 100%');

-- Sem o time, o insert abaixo inseriria zero fatias sem erro e a regra
-- ficaria vazia: aborta a migration inteira.
do $$
begin
  if not exists (select 1 from public.teams where name = 'Diego/Murillo') then
    raise exception 'time ''Diego/Murillo'' não existe em public.teams: a regra ''Time Diego/Murillo 100%%'' ficaria sem fatia'
      using errcode = '55000';
  end if;
end;
$$;

insert into public.allocation_rule_splits (rule_id, team_id, percentage)
select r.id, t.id, 100 from public.allocation_rules r, public.teams t
where r.name = 'Time Diego/Murillo 100%' and t.name = 'Diego/Murillo';

-- 6b. Regra padrão por time:
--   time Carlos        -> 'Time Carlos 100%'
--   time Weslley       -> 'Time Weslley 100%'
--   time Diego/Murillo -> 'Time Diego/Murillo 100%'
--   qualquer outro time ou perfil sem time -> NULL (rateio a resolver)
create or replace function public.default_allocation_rule_for_profile(p_profile_id uuid)
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
  elsif v_team_name = 'Diego/Murillo' then
    select id into v_rule_id from public.allocation_rules where name = 'Time Diego/Murillo 100%';
  else
    v_rule_id := null;
  end if;

  return v_rule_id;
end;
$$;

revoke execute on function public.default_allocation_rule_for_profile(uuid) from public, anon;
grant execute on function public.default_allocation_rule_for_profile(uuid) to authenticated;
