-- ============================================================
-- 025_profile_display_name.sql
-- Função pra resolver o nome de exibição de qualquer usuário (full_name,
-- com fallback pro e-mail) sem expor auth.users pro frontend. Motivada
-- pelo ranking do dashboard CRM (024_projects_read_crm.sql): owner_id de
-- projects/proposals nem sempre tem profiles.full_name preenchido (ex.:
-- Diego hoje), e a única rota que lê auth.users.email é
-- GET /api/v1/users, que é master-only — um usuário CRM comum não pode
-- chamá-la. `security definer` deixa a função ler auth.users com o
-- privilégio de quem a criou, sem precisar dar SELECT direto na tabela
-- pra quem chama via RPC.
--
-- ROLLBACK:
--   revoke execute on function profile_display_name(uuid) from authenticated;
--   drop function if exists profile_display_name(uuid);
-- ============================================================

create or replace function profile_display_name(p_profile_id uuid)
returns text
language sql
security definer
stable
as $$
  select coalesce(
    (select full_name from profiles where id = p_profile_id),
    (select email from auth.users where id = p_profile_id)
  );
$$;

grant execute on function profile_display_name(uuid) to authenticated;
