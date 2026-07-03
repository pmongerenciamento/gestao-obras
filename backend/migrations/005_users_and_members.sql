-- Migration: 005_users_and_members
-- Adiciona a tela de gestão de usuários: perfil (nome/avatar) e vínculo de
-- usuário a projeto (convite/status), separados de auth.users (gerenciado
-- pelo Supabase Auth via Admin API, ver backend/app/domain/users).
-- Referência: docs/sessao-atual.md (item 40) — "tela de gestão de usuários"

-- =========================================================
-- PERFIL (nome/avatar — auth.users já tem e-mail/senha)
-- =========================================================

create table profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    full_name   text,
    avatar_url  text,
    created_at  timestamptz not null default now()
);

-- Usuários são criados via Admin API (invite_user_by_email/create_user), que
-- insere direto em auth.users — este trigger garante que toda conta sempre
-- tem uma linha em profiles, sem depender do backend lembrar de criá-la.
-- `security definer` é obrigatório aqui: o INSERT em auth.users roda com o
-- papel interno do GoTrue (supabase_auth_admin), que não tem grant/RLS pra
-- escrever em public.profiles por conta própria — sem isso o trigger falha
-- e quebra a criação do usuário inteira ("Database error saving new user").
create function fn_handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id) values (new.id);
    return new;
end;
$$;

create trigger trg_on_auth_user_created
    after insert on auth.users
    for each row
    execute function fn_handle_new_auth_user();

-- =========================================================
-- VÍNCULO USUÁRIO x PROJETO
-- =========================================================

create table project_members (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects (id) on delete cascade,
    user_id     uuid not null references auth.users (id) on delete cascade,
    invited_by  uuid not null references auth.users (id),
    invited_at  timestamptz not null default now(),
    status      text not null default 'pending'
                check (status in ('pending', 'active', 'blocked')),
    constraint project_members_unique unique (project_id, user_id)
);

create index idx_project_members_project_id on project_members (project_id);
create index idx_project_members_user_id on project_members (user_id);

-- =========================================================
-- ROW LEVEL SECURITY
-- A gestão de verdade (criar/bloquear/excluir) passa pelo backend via
-- DATABASE_URL direto (role postgres, ignora RLS — mesma nota do item 30 de
-- docs/sessao-atual.md). Estas políticas cobrem só leitura direta do
-- frontend (ex.: exibir nome/avatar de um membro em algum outro módulo).
-- =========================================================

alter table profiles enable row level security;
alter table project_members enable row level security;

create policy profiles_read_all on profiles
    for select
    using (auth.role() = 'authenticated');

create policy profiles_self_update on profiles
    for update
    using (id = auth.uid())
    with check (id = auth.uid());

create policy project_members_self_read on project_members
    for select
    using (user_id = auth.uid());
