alter table billing_entities drop column if exists bank_name;
alter table billing_entities drop column if exists bank_agency;
alter table billing_entities drop column if exists bank_account;

-- ROLLBACK:
--   alter table billing_entities add column if not exists bank_name text;
--   alter table billing_entities add column if not exists bank_agency text;
--   alter table billing_entities add column if not exists bank_account text;
