-- ============================================================
-- 038_bank_reconciliation.sql
-- Conciliação bancária (módulo Financeiro):
--   1. bank_transactions — lançamentos do extrato bancário (Banco Inter),
--      com status de conciliação e vínculo com a despesa/parcela casada
--   2. RLS restrita ao módulo financeiro
--
-- ADITIVA: só cria tabela/índice/policy novos.
--
-- Permissão: reaproveita o resource 'expenses' já existente (037) — quem
-- concilia extrato é quem lança despesa. Não cria resource novo, então
-- não mexe no catálogo de permissões.
--
-- matched_contract_installment_id fica SEM FK por enquanto: a tabela
-- contract_installments ainda não existe (trabalho futuro, fora do escopo
-- desta migration). Quando ela for criada, adicionar:
--   alter table bank_transactions
--     add constraint bank_transactions_matched_contract_installment_id_fkey
--     foreign key (matched_contract_installment_id) references contract_installments(id);
--
-- match_confidence: o check é `in ('alto', 'medio')` (sem null na lista).
-- NULL já passa no CHECK por ser coluna nullable; colocar null dentro do
-- IN faria qualquer valor fora da lista virar NULL e passar também.
--
-- ROLLBACK:
--   drop table if exists bank_transactions;  -- (índice e policy caem junto)
-- ============================================================

create table bank_transactions (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  transaction_date date not null,
  value numeric not null,
  type text not null check (type in ('credito', 'debito')),
  payer_document text,
  payer_name text,
  description text,
  raw_payload jsonb,
  reconciliation_status text not null default 'pendente'
    check (reconciliation_status in ('pendente', 'sugerido', 'conciliado', 'ignorado')),
  matched_expense_id uuid references expenses(id),
  matched_contract_installment_id uuid,  -- sem FK: contract_installments ainda não existe (ver topo)
  match_confidence text check (match_confidence in ('alto', 'medio')),
  reconciled_by uuid references profiles(id),
  reconciled_at timestamptz,
  created_at timestamptz not null default now()
);

create index idx_bank_transactions_status on bank_transactions (reconciliation_status);

-- RLS: restrito ao módulo financeiro (mesma permissão de quem lança despesa)
alter table bank_transactions enable row level security;
create policy bank_transactions_all on bank_transactions for all to authenticated
  using (has_permission('expenses', 'write'))
  with check (has_permission('expenses', 'write'));
