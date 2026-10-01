-- ============================================================
-- 032_reimbursement_reopen_rejected.sql
-- Tela /reembolso/aprovacoes: quando o financeiro rejeita um relatório
-- (status='rejeitado'), o dono precisa conseguir corrigir e reenviar —
-- hoje `reimbursement_reports_update_own_draft` (030) só permite UPDATE
-- partindo de status='rascunho' (cláusula USING), então um relatório
-- rejeitado ficava travado: nem o dono nem ninguém sem
-- has_permission('reimbursement_reports','write') conseguia mexer nele
-- de novo.
--
-- ALTER POLICY troca só a cláusula USING, somando 'rejeitado' como
-- estado de origem válido — a cláusula WITH CHECK continua a mesma
-- (só pode virar 'rascunho' ou 'enviado'), então o dono não consegue
-- se auto-aprovar nem manter o status em 'rejeitado' via UPDATE.
--
-- ROLLBACK:
--   alter policy reimbursement_reports_update_own_draft on reimbursement_reports
--     using (profile_id = auth.uid() and status = 'rascunho')
--     with check (profile_id = auth.uid() and status in ('rascunho', 'enviado'));
-- ============================================================

alter policy reimbursement_reports_update_own_draft on reimbursement_reports
  using (profile_id = auth.uid() and status in ('rascunho', 'rejeitado'))
  with check (profile_id = auth.uid() and status in ('rascunho', 'enviado'));
