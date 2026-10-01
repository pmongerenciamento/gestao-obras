-- ============================================================
-- 033_reimbursement_reports_updated_at.sql
-- reimbursement_reports não tinha updated_at — achado ao investigar um
-- caso de status mudando pra 'enviado' sem explicação clara: sem essa
-- coluna, não dava pra saber no banco QUANDO o status mudou de fato
-- (só created_at, que é a criação original, e approved_at, que só
-- existe pra aprovação). Essa coluna + trigger fecham essa lacuna de
-- auditoria pra qualquer UPDATE futuro (reabertura, envio, aprovação,
-- rejeição).
--
-- Só em reimbursement_reports por ora — reimbursement_items nunca é
-- atualizado depois de criado (RLS de 030 só libera insert/select via
-- reimbursement_items_via_report; o with check de update/delete exige
-- report em 'rascunho' e nenhum fluxo do app faz UPDATE num item), então
-- updated_at lá não teria uso real hoje.
--
-- ROLLBACK:
--   drop trigger if exists reimbursement_reports_set_updated_at on reimbursement_reports;
--   drop function if exists set_updated_at();
--   alter table reimbursement_reports drop column if exists updated_at;
-- ============================================================

alter table reimbursement_reports
  add column updated_at timestamptz not null default now();

-- clock_timestamp(), não now(): now()/transaction_timestamp() fica
-- congelado no horário de início da transação, então múltiplos UPDATEs
-- dentro da mesma transação gravariam o mesmo updated_at.
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = clock_timestamp();
  return new;
end;
$$;

create trigger reimbursement_reports_set_updated_at
  before update on reimbursement_reports
  for each row
  execute function set_updated_at();
