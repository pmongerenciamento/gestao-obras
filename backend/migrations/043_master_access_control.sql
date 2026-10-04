-- ============================================================
-- 043_master_access_control.sql
-- Controle de acesso pelo usuário master: só quem tem
-- profiles.system_role = 'master' concede módulos (profile_modules) e
-- times (team_members).
--
-- O QUE FAZ:
--   1. public.is_master(): true se o usuário logado tem system_role =
--      'master'. security definer + search_path = '' e EXECUTE só pra
--      authenticated (mesmo padrão da 040/041).
--   2. trg_profiles_guard_system_role: system_role só muda por migration
--      ou service role (auth.uid() nulo). Hoje profiles_self_update (005)
--      + o grant de UPDATE de authenticated deixam qualquer usuário fazer
--      "update profiles set system_role = 'master'" no próprio perfil pela
--      API. Também barra INSERT com system_role preenchido: authenticated
--      tem o grant de INSERT e só não insere porque não existe policy de
--      INSERT em profiles (confirmado em produção, 2026-10-04). O trigger
--      cobre o caso de alguém criar essa policy no futuro. Não afeta
--      fn_handle_new_auth_user() (005): roda dentro do GoTrue, sem claims
--      (auth.uid() nulo), e não preenche system_role.
--   3. trg_profiles_protect_last_master: impede rebaixar ou apagar o
--      único master. ABSOLUTO, vale também pro postgres e pro service
--      role.
--   4. profile_modules: escrita (e leitura de todas as linhas) só pro
--      master. Sai profile_modules_write_financeiro (019);
--      profile_modules_select_own continua.
--   5. team_members: escrita só pro master. Sai team_members_write (023);
--      team_members_read continua. A linha ('financeiro', 'team_members',
--      read, write) do catálogo de permissões (023) fica onde está:
--      has_permission() não muda, só deixa de decidir a escrita em
--      team_members.
--   teams e as demais tabelas não mudam.
--
-- TROCAR DE MASTER: promova o novo primeiro e só depois rebaixe o
-- antigo, os dois por migration ou service role. Na ordem inversa, o
-- trigger do item 3 bloqueia.
--
-- APAGAR A CONTA DO ÚNICO MASTER fica bloqueado: profiles.id referencia
-- auth.users(id) com ON DELETE CASCADE (005). O delete em cascata dispara
-- o trigger do item 3, que aborta o delete da conta inteira (inclusive
-- pela Admin API / tela /usuarios). Pendência: a tela /usuarios deve
-- mostrar uma mensagem clara nesse caso em vez de um erro genérico.
--
-- SAÍDA DE EMERGÊNCIA (só de propósito, por quem tem acesso de dono ao
-- banco, e reabilitando em seguida):
--   alter table public.profiles disable trigger trg_profiles_protect_last_master;
--   -- ... operação ...
--   alter table public.profiles enable trigger trg_profiles_protect_last_master;
--
-- ROLLBACK (na ordem; não mexe nos valores de system_role já gravados):
--   drop policy if exists team_members_write_master on public.team_members;
--   create policy team_members_write on public.team_members
--     for all to authenticated
--     using (public.has_permission('team_members', 'write'))
--     with check (public.has_permission('team_members', 'write'));
--   drop policy if exists profile_modules_select_master on public.profile_modules;
--   drop policy if exists profile_modules_write_master on public.profile_modules;
--   create policy profile_modules_write_financeiro on public.profile_modules
--     for all to authenticated
--     using (public.has_module_access('financeiro'))
--     with check (public.has_module_access('financeiro'));
--   grant execute on function public.fn_profiles_protect_last_master() to public, anon, authenticated;
--   grant execute on function public.fn_profiles_guard_system_role() to public, anon, authenticated;
--   (os dois grants acima só importam se as funções forem mantidas;
--    os drops abaixo removem as funções de qualquer forma)
--   drop trigger if exists trg_profiles_protect_last_master on public.profiles;
--   drop function if exists public.fn_profiles_protect_last_master();
--   drop trigger if exists trg_profiles_guard_system_role on public.profiles;
--   drop function if exists public.fn_profiles_guard_system_role();
--   drop function if exists public.is_master();
-- ============================================================

-- 1. is_master()
create function public.is_master()
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and system_role = 'master'
  );
$$;

revoke execute on function public.is_master() from public, anon;
grant execute on function public.is_master() to authenticated;

-- 2. system_role só muda por migration ou service role
-- Funções de trigger (itens 2 e 3): o Postgres não deixa chamar uma
-- função "returns trigger" diretamente e o PostgREST não as expõe como
-- RPC, mas toda função nasce com EXECUTE para PUBLIC. O revoke logo após
-- cada uma tira esse privilégio de public, anon e authenticated, pra que
-- has_function_privilege() também dê false (diferente da 041, que deixou
-- as de trigger sem revoke). Não afeta o disparo: o EXECUTE da função de
-- trigger só é conferido no CREATE TRIGGER (feito pelo dono da migration),
-- não a cada disparo.
create function public.fn_profiles_guard_system_role()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if auth.uid() is null then
    return new;
  end if;

  if tg_op = 'INSERT' and new.system_role is not null then
    raise exception 'system_role não pode ser definido pela API (só por migration ou service role)'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' and new.system_role is distinct from old.system_role then
    raise exception 'system_role não pode ser alterado pela API (só por migration ou service role)'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke execute on function public.fn_profiles_guard_system_role() from public, anon, authenticated;

create trigger trg_profiles_guard_system_role
  before insert or update of system_role on public.profiles
  for each row
  execute function public.fn_profiles_guard_system_role();

-- 3. Proteção do último master (absoluta)
-- security definer: a contagem precisa enxergar todos os perfis,
-- independente de RLS de quem disparou. O advisory lock serializa
-- rebaixamentos/deletes concorrentes de masters: sem ele, duas transações
-- rebaixando dois masters ao mesmo tempo poderiam cada uma ver a outra
-- como "o master que sobra" e zerar os masters.
create function public.fn_profiles_protect_last_master()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.system_role is distinct from 'master' then
    return case when tg_op = 'DELETE' then old else new end;
  end if;

  if tg_op = 'UPDATE' and new.system_role is not distinct from 'master' then
    return new;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('public.profiles:master'));

  if not exists (
    select 1 from public.profiles
    where system_role = 'master' and id <> old.id
  ) then
    raise exception 'não é possível rebaixar ou apagar o único master: promova outro master antes'
      using errcode = '42501';
  end if;

  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

revoke execute on function public.fn_profiles_protect_last_master() from public, anon, authenticated;

create trigger trg_profiles_protect_last_master
  before update or delete on public.profiles
  for each row
  execute function public.fn_profiles_protect_last_master();

-- 4. profile_modules: só o master concede
-- drop sem "if exists" de propósito: se a policy tiver outro nome no
-- banco, a migration falha em vez de deixar a regra antiga ativa.
drop policy profile_modules_write_financeiro on public.profile_modules;

create policy profile_modules_write_master on public.profile_modules
  for all to authenticated
  using (public.is_master())
  with check (public.is_master());

create policy profile_modules_select_master on public.profile_modules
  for select to authenticated
  using (public.is_master());

-- 5. team_members: só o master concede
drop policy team_members_write on public.team_members;

create policy team_members_write_master on public.team_members
  for all to authenticated
  using (public.is_master())
  with check (public.is_master());
