-- clients (2 policies existentes: clients_select_authenticated, clients_write_authenticated)
drop policy if exists clients_select_authenticated on clients;
drop policy if exists clients_write_authenticated on clients;
create policy clients_write_crm on clients
  for all to authenticated
  using (has_module_access('crm'))
  with check (has_module_access('crm'));
create policy clients_select_crm_financeiro on clients
  for select to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'));

-- billing_entities (2 policies existentes: billing_entities_select_authenticated, billing_entities_write_authenticated)
drop policy if exists billing_entities_select_authenticated on billing_entities;
drop policy if exists billing_entities_write_authenticated on billing_entities;
create policy billing_entities_write_crm_financeiro on billing_entities
  for all to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'))
  with check (has_module_access('crm') or has_module_access('financeiro'));
create policy billing_entities_select_crm_financeiro on billing_entities
  for select to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'));

-- contracts (1 policy existente: contracts_all_authenticated)
drop policy if exists contracts_all_authenticated on contracts;
create policy contracts_write_crm on contracts
  for all to authenticated
  using (has_module_access('crm'))
  with check (has_module_access('crm'));
create policy contracts_select_crm_financeiro on contracts
  for select to authenticated
  using (has_module_access('crm') or has_module_access('financeiro'));

-- ROLLBACK: recriar as policies "_authenticated" originais com
-- using(true)/with check(true), revertendo pro fallback anterior.
