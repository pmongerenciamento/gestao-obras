-- ============================================================
-- 036_deprecate_team_cost_allocations.sql
-- Fase B (final) do módulo Financeiro: marca team_cost_allocations
-- (migration 030) como DEPRECATED, agora que o rateio é resolvido por
-- allocation_rules/allocation_rule_splits (034) e gravado em
-- reimbursement_items.allocation_rule_id pelo código do Reembolso
-- (createItem, via default_allocation_rule_for_profile — 035).
--
-- NÃO apaga dado: a tabela e suas linhas ficam como histórico de
-- referência. Apenas:
--   1. documenta a depreciação via comentário na própria tabela;
--   2. revoga a ESCRITA (drop da policy team_cost_allocations_write,
--      criada na 030), mantendo a LEITURA (team_cost_allocations_read)
--      para consulta histórica.
-- DROP TABLE fica para uma limpeza futura, decisão separada.
--
-- Verificado nesta data: nenhum código de frontend/backend lê ou
-- escreve team_cost_allocations (única menção é um comentário em
-- frontend/lib/api/reimbursement-mutations.ts).
--
-- ROLLBACK:
--   comment on table team_cost_allocations is null;
--   create policy team_cost_allocations_write on team_cost_allocations for all to authenticated
--     using (has_permission('reimbursement_reports', 'write'))
--     with check (has_permission('reimbursement_reports', 'write'));
-- ============================================================

comment on table team_cost_allocations is
  'DEPRECATED desde migration 036 — substituída por allocation_rules/allocation_rule_splits. Mantida só como histórico, não usada em código novo. Candidata a DROP numa limpeza futura.';

-- Revoga a escrita (mantém a leitura para histórico). if exists: robusto
-- caso a policy já tenha sido removida em algum ambiente.
drop policy if exists team_cost_allocations_write on team_cost_allocations;
