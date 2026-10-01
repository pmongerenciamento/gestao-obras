-- ============================================================
-- 028_client_legal_fields.sql
-- Campos jurídicos pra fechamento de negócio (close_deal(), migration
-- 029): dados do cliente (endereço, representante legal) e a data de
-- assinatura do contrato (distinta de contracts.start_date — quando foi
-- assinado vs. quando o serviço começa).
--
-- ROLLBACK:
--   alter table contracts drop column if exists signed_date;
--   alter table clients drop column if exists legal_rep_role;
--   alter table clients drop column if exists legal_rep_cpf;
--   alter table clients drop column if exists legal_rep_name;
--   alter table clients drop column if exists address;
-- ============================================================

alter table clients add column address text;
alter table clients add column legal_rep_name text;
alter table clients add column legal_rep_cpf text;
alter table clients add column legal_rep_role text;

alter table contracts add column signed_date date;
