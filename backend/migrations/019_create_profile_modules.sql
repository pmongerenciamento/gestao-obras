-- ============================================================
-- 019_create_profile_modules.sql
-- Controle de acesso por módulo (crm/financeiro/engenharia/reembolso) por
-- usuário — base pra substituir os fallbacks "to authenticated" deixados
-- como TODO nas migrations 016/017/018 por has_module_access(...) de
-- verdade.
--
-- has_module_access() é `security definer`: roda com o dono da função
-- (quem aplicou a migration), que não está sujeito à própria RLS de
-- profile_modules — sem isso, a policy de escrita abaixo (que chama a
-- função) recairia sobre a mesma tabela que a função consulta e cairia em
-- recursão/negação (RLS não se aplica ao dono da tabela por padrão, é
-- esse detalhe que evita o problema).
--
-- ROLLBACK:
--   drop policy if exists profile_modules_select_own on profile_modules;
--   drop policy if exists profile_modules_write_financeiro on profile_modules;
--   alter table profile_modules disable row level security;
--   drop function if exists has_module_access(text);
--   drop table if exists profile_modules;
-- ============================================================

create table profile_modules (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references profiles(id) on delete cascade,
  module text not null check (module in ('crm', 'financeiro', 'engenharia', 'reembolso')),
  created_at timestamptz not null default now(),
  unique (profile_id, module)
);

create or replace function has_module_access(module_name text)
returns boolean as $$
  select exists (
    select 1 from profile_modules
    where profile_id = auth.uid() and module = module_name
  );
$$ language sql security definer stable;

alter table profile_modules enable row level security;

-- Só o próprio usuário lê seus módulos (evita expor quem tem acesso a quê
-- pra qualquer autenticado). Escrita fica só pra quem já tem módulo
-- 'financeiro' (é decisão de sócio conceder acesso).
create policy profile_modules_select_own on profile_modules
  for select to authenticated using (profile_id = auth.uid());

create policy profile_modules_write_financeiro on profile_modules
  for all to authenticated
  using (has_module_access('financeiro'))
  with check (has_module_access('financeiro'));

-- Seed inicial (ajustar profile_id reais antes de rodar):
-- Diego e Murillo: todos os 4 módulos
-- Carlos e Weslley: crm, financeiro, engenharia
-- Camila e Thiago: engenharia, reembolso
