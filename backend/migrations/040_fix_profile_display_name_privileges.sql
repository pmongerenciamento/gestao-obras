-- ============================================================
-- 040_fix_profile_display_name_privileges.sql
-- Fecha acesso anônimo a profile_display_name() (025).
--
-- CAUSA: toda função nova no Postgres nasce com EXECUTE para PUBLIC, e o
-- Supabase ainda concede EXECUTE a anon por default privileges. A 025 só
-- fez "grant ... to authenticated", sem revogar o resto — então anon
-- conseguia chamar a função via RPC, sem login, e obter nome ou e-mail
-- (lido de auth.users, a função é security definer) de qualquer usuário
-- a partir do id. Os ids não são secretos: o bucket público
-- avatar-images guarda arquivos em {user_id}/ e a policy
-- avatar_images_select_public permite listar. Confirmado em staging
-- (2026-10-04) com has_function_privilege('anon', ...) = true.
--
-- Também fixa search_path = '' (função security definer sem search_path
-- fixo é alerta conhecido do linter do Supabase) e qualifica as tabelas
-- com schema. O corpo da função é o mesmo da 025.
--
-- authenticated continua podendo executar (uso pretendido: ranking do
-- dashboard CRM, ver 025).
--
-- ROLLBACK (reabre o acesso anônimo):
--   grant execute on function profile_display_name(uuid) to public, anon;
--   (e recriar a função sem "set search_path", conforme a 025)
-- ============================================================

create or replace function profile_display_name(p_profile_id uuid)
returns text
language sql
security definer
stable
set search_path = ''
as $$
  select coalesce(
    (select full_name from public.profiles where id = p_profile_id),
    (select email from auth.users where id = p_profile_id)
  );
$$;

revoke execute on function profile_display_name(uuid) from public, anon;
grant execute on function profile_display_name(uuid) to authenticated;
