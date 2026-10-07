-- ============================================================
-- 050_billing_registry.sql
-- Cadastro de faturamento: perfil fiscal da SPE, destinatários da nota,
-- dados fiscais do contrato com vigência, regime tributário da empresa e
-- taxa do DRE por mês. Só tabelas NOVAS; nenhuma tabela existente muda.
--
-- REGRA: o tomador da nota é sempre a SPE (public.billing_entities). O CNPJ
-- e a razão social ficam só em billing_entities; aqui fica o resto do que a
-- nota precisa. Os dados fiscais são opcionais até a emissão automática
-- (janeiro): a falta deles aparece na visão de completude (posterior), não
-- como erro de gravação.
--
-- O QUE FAZ:
--   1. public.taxpayer_profiles: um perfil fiscal por SPE
--      (billing_entity_id único, FK sem cascade). Todos os campos aceitam
--      nulo (o perfil pode ser salvo parcial; o que falta aparece na
--      completude): inscrição municipal e estadual, endereço estruturado
--      (rua, número, complemento, bairro, município) e, com check de
--      formato quando preenchidos, código IBGE com 7 dígitos, UF com 2
--      letras maiúsculas e CEP com 8 dígitos. Sem DELETE pela API.
--      billing_entities.address (texto livre, gravado pelo close_deal)
--      continua existindo e não é lido daqui.
--   2. public.billing_contacts: destinatários da nota. Exatamente um entre
--      billing_entity_id (lista padrão da SPE) e contract_id (lista do
--      contrato). REGRA DE USO: vale a lista do contrato se ela tiver ao
--      menos um 'para' ativo; senão, vale a lista da SPE do projeto do
--      contrato. Um e-mail por lista (índices únicos parciais por dono e
--      lower(email)). Sem DELETE pela API: o contato sai com active = false.
--   3. public.contract_fiscal_settings: versões por contrato, valid_from
--      no dia 1, única por (contract_id, valid_from); cada versão vale até
--      a próxima do mesmo contrato. Todas as colunas fiscais são opcionais.
--      Sem DELETE pela API: versão errada se corrige por UPDATE.
--      Percentuais (ISS e retenções) de 0 a 100. Sem tomador (é sempre a
--      SPE) e sem conta de cobrança (vale destination_account da parcela).
--      Sem dia de emissão: ver DOCUMENT_LEAD_DAYS abaixo.
--   4. public.company_tax_regimes: regime da empresa por vigência
--      (valid_from no dia 1 é a chave; cada linha vale até a próxima).
--      Seed: só 'simples' desde 2026-01-01 (a passagem para o lucro
--      presumido não está confirmada). Só o master grava (item 6). Trigger
--      recusa (55000) mudar a vigência de parcela já emitida ou recebida:
--      ver REGIME E PARCELAS abaixo.
--   5. public.dre_tax_rates: taxa do DRE por mês (month no dia 1 é a
--      chave), rate como fração (0 < rate < 1). Seed: 2026-06-01 e
--      2026-07-01 com 0,167 ('confirmado nos DRE de junho e julho'). Sem
--      DELETE pela API: corrige-se por UPDATE.
--   6. Catálogo e RLS no padrão has_permission() da 023/045/047:
--        taxpayer_profiles, billing_contacts, contract_fiscal_settings:
--          financeiro lê e grava; crm lê.
--        company_tax_regimes: financeiro e crm leem pelo catálogo, e o
--          master lê mesmo sem módulo (has_permission(...) or
--          public.is_master()); ninguém grava pelo catálogo;
--          insert/update/delete só com public.is_master().
--        dre_tax_rates: financeiro lê e grava.
--      EXCEÇÃO DO is_master(): nas tabelas de dado a regra é has_permission
--      (módulo), e is_master() fica para controle de acesso (043) e para o
--      retroativo da divisão (048). O regime é a exceção porque não é dado
--      de um módulo: vale para a empresa toda e muda, de uma vez, o
--      tratamento fiscal de todas as notas e o DRE de todos os meses da
--      vigência. Dar gravação ao módulo financeiro deixaria qualquer pessoa
--      do financeiro trocar isso; a decisão é do sócio master.
--   7. created_by em contract_fiscal_settings, company_tax_regimes e
--      dre_tax_rates: no INSERT pela API vira auth.uid() (não dá para gravar
--      outro usuário); no UPDATE não muda. Fica nulo quando não há usuário
--      logado (migration), como nos seeds desta migration: a migration não
--      tem sessão, e resolver o id do Diego aqui exigiria escrever o e-mail
--      dele no arquivo, que é o que se está tirando dos scripts. A origem
--      dos seeds fica em notes.
--   8. updated_at com public.set_updated_at() (033/037) em
--      taxpayer_profiles, billing_contacts, contract_fiscal_settings e
--      dre_tax_rates. company_tax_regimes não tem updated_at (pedido assim:
--      uma linha de regime não deve ser editada depois de usada).
--   9. Privilégios: anon e public sem nada; authenticated sem TRUNCATE,
--      REFERENCES e TRIGGER; DELETE só em company_tax_regimes (e lá só o
--      master passa pela policy); taxpayer_profiles, billing_contacts,
--      contract_fiscal_settings e dre_tax_rates ficam com select, insert e
--      update. EXECUTE das funções de trigger e da contagem revogado de
--      public, anon e authenticated (como na 043 e na 045).
--
-- DOCUMENT_LEAD_DAYS: contracts.document_lead_days (018) não tem significado
-- documentado (sem comentário nem documentação) e não é usado no backend
-- nem no frontend (conferido em 2026-10-07). Esta migration não o usa e não
-- cria dia de emissão: a emissão automática (janeiro) define o campo certo.
--
-- REGIME E PARCELAS: a vigência de uma linha de regime é
-- [valid_from, próximo valid_from). Uma parcela "está na vigência" se
-- status in ('emitida', 'recebida') e qualquer uma destas datas cai nela:
-- issue_date (data da nota), received_date (recebida sem nota, ex.: conta
-- PF, não tem issue_date; o check da 045 só exige issue_date em 'emitida')
-- ou competencia_month (mês do DRE). As três de uma vez é conservador de
-- propósito. 'cancelada' não conta. O trigger recusa:
--   - DELETE de uma linha com parcela na vigência dela;
--   - UPDATE de valid_from ou regime com parcela na vigência antiga ou na
--     nova (UPDATE só de notes passa);
--   - INSERT que abra vigência nova sobre parcela já travada (inserir uma
--     linha encurta a vigência da anterior: é o mesmo efeito de alterar).
-- Vale para todo mundo, inclusive migration e service role: é regra de
-- dado, não de API. A saída de emergência é desligar o gatilho de propósito
-- (alter table ... disable trigger trg_company_tax_regimes_guard), corrigir
-- e religar, numa migration revisada.
-- CONSEQUÊNCIA PRÁTICA: a linha do lucro presumido (ou de qualquer novo
-- regime) tem que entrar ANTES de emitir ou receber qualquer parcela da nova
-- vigência, inclusive nota emitida antes da virada com vencimento
-- (competencia_month) dentro dela. Depois disso a vigência fica travada.
--
-- NÃO FAZ (fica para as próximas): SPE do contrato (mesma SPE em projetos
-- diferentes; hoje billing_entities é uma por projeto e o CNPJ é único);
-- bloqueio de INSERT de contrato já 'encerrado'; visão de completude;
-- views do DRE; cópia de campos no close_deal; tirar 'parcelado' dos checks.
--
-- ROLLBACK (na ordem; apaga tudo o que foi gravado nessas tabelas):
--   drop table if exists public.dre_tax_rates;             -- triggers caem junto
--   drop table if exists public.company_tax_regimes;
--   drop table if exists public.contract_fiscal_settings;
--   drop table if exists public.billing_contacts;
--   drop table if exists public.taxpayer_profiles;
--   drop function if exists public.fn_company_tax_regimes_guard();
--   drop function if exists public.fn_tax_regime_locked_count(date, date);
--   drop function if exists public.fn_set_created_by();
--   delete from public.permissions where resource_key in
--     ('taxpayer_profiles', 'billing_contacts', 'contract_fiscal_settings',
--      'company_tax_regimes', 'dre_tax_rates');
--   delete from public.resources where key in
--     ('taxpayer_profiles', 'billing_contacts', 'contract_fiscal_settings',
--      'company_tax_regimes', 'dre_tax_rates');
--   -- NÃO dropar public.set_updated_at(): compartilhada (033/037/045).
-- ============================================================

-- 0. created_by: auth.uid() no insert pela API, imutável no update
-- Sem security definer: auth.uid() lê o JWT da própria requisição.
create function public.fn_set_created_by()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if auth.uid() is not null then
      new.created_by := auth.uid();
    end if;
  else
    new.created_by := old.created_by;
  end if;
  return new;
end;
$$;

revoke execute on function public.fn_set_created_by() from public, anon, authenticated;

-- 1. taxpayer_profiles (perfil fiscal da SPE)
create table public.taxpayer_profiles (
  id uuid primary key default gen_random_uuid(),
  billing_entity_id uuid not null unique references public.billing_entities(id),
  municipal_registration text check (municipal_registration is null or btrim(municipal_registration) <> ''),
  state_registration text check (state_registration is null or btrim(state_registration) <> ''),
  street text check (street is null or btrim(street) <> ''),
  street_number text check (street_number is null or btrim(street_number) <> ''),  -- texto: aceita 'S/N'
  complement text check (complement is null or btrim(complement) <> ''),
  district text check (district is null or btrim(district) <> ''),
  city_name text check (city_name is null or btrim(city_name) <> ''),
  city_ibge_code text check (city_ibge_code is null or city_ibge_code ~ '^[0-9]{7}$'),
  state text check (state is null or state ~ '^[A-Z]{2}$'),
  zip_code text check (zip_code is null or zip_code ~ '^[0-9]{8}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger taxpayer_profiles_set_updated_at
  before update on public.taxpayer_profiles
  for each row execute function public.set_updated_at();

-- 2. billing_contacts (destinatários da nota)
create table public.billing_contacts (
  id uuid primary key default gen_random_uuid(),
  billing_entity_id uuid references public.billing_entities(id),
  contract_id uuid references public.contracts(id),
  name text check (name is null or btrim(name) <> ''),
  email text not null check (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  role text not null check (role in ('para', 'copia')),
  active boolean not null default true,
  origin text check (origin is null or btrim(origin) <> ''),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint billing_contacts_one_owner check (num_nonnulls(billing_entity_id, contract_id) = 1)
);

-- um e-mail por lista (sem diferenciar maiúsculas); servem também de índice da FK
create unique index uq_billing_contacts_billing_entity_email
  on public.billing_contacts (billing_entity_id, lower(email))
  where billing_entity_id is not null;
create unique index uq_billing_contacts_contract_email
  on public.billing_contacts (contract_id, lower(email))
  where contract_id is not null;

create trigger billing_contacts_set_updated_at
  before update on public.billing_contacts
  for each row execute function public.set_updated_at();

-- 3. contract_fiscal_settings (versões por contrato)
create table public.contract_fiscal_settings (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts(id),
  valid_from date not null check (extract(day from valid_from) = 1),
  service_code_lc116 text check (service_code_lc116 is null or btrim(service_code_lc116) <> ''),
  national_tax_code text check (national_tax_code is null or btrim(national_tax_code) <> ''),
  nbs_code text check (nbs_code is null or btrim(nbs_code) <> ''),
  invoice_description text check (invoice_description is null or btrim(invoice_description) <> ''),
  service_location_ibge_code text check (service_location_ibge_code is null or service_location_ibge_code ~ '^[0-9]{7}$'),
  iss_rate_pct numeric(5,2) check (iss_rate_pct is null or (iss_rate_pct >= 0 and iss_rate_pct <= 100)),
  iss_withheld boolean,
  pis_withheld_pct numeric(5,2) check (pis_withheld_pct is null or (pis_withheld_pct >= 0 and pis_withheld_pct <= 100)),
  cofins_withheld_pct numeric(5,2) check (cofins_withheld_pct is null or (cofins_withheld_pct >= 0 and cofins_withheld_pct <= 100)),
  csll_withheld_pct numeric(5,2) check (csll_withheld_pct is null or (csll_withheld_pct >= 0 and csll_withheld_pct <= 100)),
  irrf_withheld_pct numeric(5,2) check (irrf_withheld_pct is null or (irrf_withheld_pct >= 0 and irrf_withheld_pct <= 100)),
  inss_withheld_pct numeric(5,2) check (inss_withheld_pct is null or (inss_withheld_pct >= 0 and inss_withheld_pct <= 100)),
  collection_method text check (collection_method is null or collection_method in ('boleto', 'pix')),
  client_order_reference text check (client_order_reference is null or btrim(client_order_reference) <> ''),
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint contract_fiscal_settings_unique unique (contract_id, valid_from)
);

create trigger contract_fiscal_settings_set_created_by
  before insert or update on public.contract_fiscal_settings
  for each row execute function public.fn_set_created_by();

create trigger contract_fiscal_settings_set_updated_at
  before update on public.contract_fiscal_settings
  for each row execute function public.set_updated_at();

-- 4. company_tax_regimes (regime da empresa por vigência)
create table public.company_tax_regimes (
  valid_from date primary key check (extract(day from valid_from) = 1),
  regime text not null check (regime in ('simples', 'lucro_presumido')),
  notes text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

-- Seed antes do trigger de guarda (a guarda vale para as gravações seguintes).
insert into public.company_tax_regimes (valid_from, regime, notes) values
  ('2026-01-01', 'simples', 'seed da 050; passagem para o lucro presumido não confirmada');

-- Quantas parcelas emitidas ou recebidas caem em [p_from, p_to)
-- (p_to nulo = sem fim). security definer: precisa ver todas as parcelas,
-- sem depender da RLS de quem grava o regime (o master pode não ter
-- leitura de parcelas pelo módulo).
create function public.fn_tax_regime_locked_count(p_from date, p_to date)
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select count(*)::integer
  from public.contract_installments i
  where i.status in ('emitida', 'recebida')
    and (   (i.issue_date >= p_from and (p_to is null or i.issue_date < p_to))
         or (i.received_date >= p_from and (p_to is null or i.received_date < p_to))
         or (i.competencia_month >= p_from and (p_to is null or i.competencia_month < p_to)));
$$;

revoke execute on function public.fn_tax_regime_locked_count(date, date) from public, anon, authenticated;

create function public.fn_company_tax_regimes_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_to date;
  v_n integer;
begin
  -- UPDATE só de notes não muda vigência nem regime
  if tg_op = 'UPDATE' and new.valid_from = old.valid_from and new.regime = old.regime then
    return new;
  end if;

  -- vigência antiga (DELETE e UPDATE): [old.valid_from, próxima)
  if tg_op in ('UPDATE', 'DELETE') then
    select min(valid_from) into v_to
    from public.company_tax_regimes where valid_from > old.valid_from;
    v_n := public.fn_tax_regime_locked_count(old.valid_from, v_to);
    if v_n > 0 then
      raise exception 'há % parcela(s) emitida(s) ou recebida(s) na vigência de % a %: o regime dessa vigência não pode mudar',
        v_n, old.valid_from, coalesce(v_to::text, 'sem fim')
        using errcode = '55000';
    end if;
  end if;

  -- vigência nova (INSERT e UPDATE): [new.valid_from, próxima), sem contar a
  -- própria linha antiga no UPDATE
  if tg_op in ('INSERT', 'UPDATE') then
    select min(valid_from) into v_to
    from public.company_tax_regimes
    where valid_from > new.valid_from
      and (tg_op = 'INSERT' or valid_from <> old.valid_from);
    v_n := public.fn_tax_regime_locked_count(new.valid_from, v_to);
    if v_n > 0 then
      raise exception 'há % parcela(s) emitida(s) ou recebida(s) a partir de % (até %): não é possível abrir ou mover uma vigência sobre elas',
        v_n, new.valid_from, coalesce(v_to::text, 'sem fim')
        using errcode = '55000';
    end if;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

revoke execute on function public.fn_company_tax_regimes_guard() from public, anon, authenticated;

create trigger trg_company_tax_regimes_guard
  before insert or update or delete on public.company_tax_regimes
  for each row execute function public.fn_company_tax_regimes_guard();

create trigger company_tax_regimes_set_created_by
  before insert or update on public.company_tax_regimes
  for each row execute function public.fn_set_created_by();

-- 5. dre_tax_rates (taxa do DRE por mês)
create table public.dre_tax_rates (
  month date primary key check (extract(day from month) = 1),
  rate numeric(8,6) not null check (rate > 0 and rate < 1),
  notes text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.dre_tax_rates (month, rate, notes) values
  ('2026-06-01', 0.167, 'confirmado nos DRE de junho e julho'),
  ('2026-07-01', 0.167, 'confirmado nos DRE de junho e julho');

create trigger dre_tax_rates_set_created_by
  before insert or update on public.dre_tax_rates
  for each row execute function public.fn_set_created_by();

create trigger dre_tax_rates_set_updated_at
  before update on public.dre_tax_rates
  for each row execute function public.set_updated_at();

-- 6. Catálogo
insert into public.resources (key, label) values
  ('taxpayer_profiles', 'Perfil fiscal da SPE'),
  ('billing_contacts', 'Destinatários da nota'),
  ('contract_fiscal_settings', 'Dados fiscais do contrato'),
  ('company_tax_regimes', 'Regime tributário da empresa'),
  ('dre_tax_rates', 'Taxa do DRE por mês');

insert into public.permissions (module_code, resource_key, can_read, can_write) values
  ('financeiro', 'taxpayer_profiles', true, true),
  ('crm', 'taxpayer_profiles', true, false),
  ('financeiro', 'billing_contacts', true, true),
  ('crm', 'billing_contacts', true, false),
  ('financeiro', 'contract_fiscal_settings', true, true),
  ('crm', 'contract_fiscal_settings', true, false),
  ('financeiro', 'company_tax_regimes', true, false),
  ('crm', 'company_tax_regimes', true, false),
  ('financeiro', 'dre_tax_rates', true, true);

-- 7. RLS e privilégios
alter table public.taxpayer_profiles enable row level security;
alter table public.billing_contacts enable row level security;
alter table public.contract_fiscal_settings enable row level security;
alter table public.company_tax_regimes enable row level security;
alter table public.dre_tax_rates enable row level security;

create policy taxpayer_profiles_read on public.taxpayer_profiles
  for select to authenticated
  using (public.has_permission('taxpayer_profiles', 'read'));
-- taxpayer_profiles: sem policy nem grant de DELETE
create policy taxpayer_profiles_insert on public.taxpayer_profiles
  for insert to authenticated
  with check (public.has_permission('taxpayer_profiles', 'write'));
create policy taxpayer_profiles_update on public.taxpayer_profiles
  for update to authenticated
  using (public.has_permission('taxpayer_profiles', 'write'))
  with check (public.has_permission('taxpayer_profiles', 'write'));

-- billing_contacts: sem policy nem grant de DELETE
create policy billing_contacts_read on public.billing_contacts
  for select to authenticated
  using (public.has_permission('billing_contacts', 'read'));
create policy billing_contacts_insert on public.billing_contacts
  for insert to authenticated
  with check (public.has_permission('billing_contacts', 'write'));
create policy billing_contacts_update on public.billing_contacts
  for update to authenticated
  using (public.has_permission('billing_contacts', 'write'))
  with check (public.has_permission('billing_contacts', 'write'));

create policy contract_fiscal_settings_read on public.contract_fiscal_settings
  for select to authenticated
  using (public.has_permission('contract_fiscal_settings', 'read'));
-- contract_fiscal_settings: sem policy nem grant de DELETE
create policy contract_fiscal_settings_insert on public.contract_fiscal_settings
  for insert to authenticated
  with check (public.has_permission('contract_fiscal_settings', 'write'));
create policy contract_fiscal_settings_update on public.contract_fiscal_settings
  for update to authenticated
  using (public.has_permission('contract_fiscal_settings', 'write'))
  with check (public.has_permission('contract_fiscal_settings', 'write'));

-- company_tax_regimes: leitura pelo catálogo ou pelo master (que grava e
-- precisa ver as linhas mesmo sem módulo); gravação só do master (item 6)
create policy company_tax_regimes_read on public.company_tax_regimes
  for select to authenticated
  using (public.has_permission('company_tax_regimes', 'read') or public.is_master());
create policy company_tax_regimes_insert_master on public.company_tax_regimes
  for insert to authenticated
  with check (public.is_master());
create policy company_tax_regimes_update_master on public.company_tax_regimes
  for update to authenticated
  using (public.is_master())
  with check (public.is_master());
create policy company_tax_regimes_delete_master on public.company_tax_regimes
  for delete to authenticated
  using (public.is_master());

-- dre_tax_rates: sem policy nem grant de DELETE
create policy dre_tax_rates_read on public.dre_tax_rates
  for select to authenticated
  using (public.has_permission('dre_tax_rates', 'read'));
create policy dre_tax_rates_insert on public.dre_tax_rates
  for insert to authenticated
  with check (public.has_permission('dre_tax_rates', 'write'));
create policy dre_tax_rates_update on public.dre_tax_rates
  for update to authenticated
  using (public.has_permission('dre_tax_rates', 'write'))
  with check (public.has_permission('dre_tax_rates', 'write'));

-- Privilégios explícitos (não depende dos default privileges do projeto)
revoke all on table
  public.taxpayer_profiles,
  public.billing_contacts,
  public.contract_fiscal_settings,
  public.company_tax_regimes,
  public.dre_tax_rates
from public, anon, authenticated;

grant select, insert, update, delete on table
  public.company_tax_regimes
to authenticated;

grant select, insert, update on table
  public.taxpayer_profiles,
  public.billing_contacts,
  public.contract_fiscal_settings,
  public.dre_tax_rates
to authenticated;
