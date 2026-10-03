-- ============================================================
-- 042_expenses_vendor_contract_link.sql
-- Liga a despesa ao contrato de fornecedor de origem (vendor_contracts,
-- migration 037). Pré-requisito do matching do extrato bancário
-- (bank_transactions, 038): o nível ALTO só vale quando a despesa vem de
-- um vendor_contract com CNPJ — e expenses não tinha como chegar a esse
-- CNPJ (só vendor_name em texto livre). Confirmado no schema real
-- (staging e produção, 2026-10-04): nenhuma coluna/FK ligava as duas.
--
-- Coluna opcional: despesa avulsa (sem contrato) continua possível.
--
-- FK SEM "on delete" explícito, DE PROPÓSITO: o padrão do Postgres
-- (NO ACTION — na prática bloqueia como RESTRICT) impede apagar um
-- vendor_contract que tenha expenses vinculadas. Despesa não pode perder
-- o vínculo com o contrato de origem silenciosamente; pra descontinuar
-- um fornecedor, usa-se vendor_contracts.status = 'encerrado', não
-- exclusão.
--
-- ADITIVA: expenses estava vazia em staging e produção ao criar esta
-- migration.
--
-- ROLLBACK:
--   drop index if exists idx_expenses_vendor_contract;
--   alter table expenses drop column if exists vendor_contract_id;  -- (a FK cai junto)
-- ============================================================

alter table expenses add column vendor_contract_id uuid references vendor_contracts(id);
create index idx_expenses_vendor_contract on expenses (vendor_contract_id);
