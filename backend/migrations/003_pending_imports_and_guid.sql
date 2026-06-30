-- Migration: 003_pending_imports_and_guid
-- Adiciona identificador estável do projeto (GUID do MS Project) e a tabela
-- de importações pendentes de confirmação (mudança estrutural detectada).
-- Referência: docs/referencia-projeto.md (seção 3) — "Mudança estrutural: sistema
-- detecta novas tarefas ou vínculos → alerta o usuário e solicita confirmação"

-- =========================================================
-- GUID ESTÁVEL DO PROJETO
-- Nome do projeto é editável pelo usuário no MS Project; o GUID interno
-- (ProjectProperties.getGUID() via MPXJ) não muda entre exportações.
-- =========================================================

alter table projects add column ms_project_guid text;

create unique index idx_projects_owner_guid
    on projects (owner_id, ms_project_guid)
    where ms_project_guid is not null;

-- =========================================================
-- IMPORTAÇÕES PENDENTES DE CONFIRMAÇÃO
-- Guarda o resultado já parseado de um upload que alterou a estrutura
-- (tasks/dependências novas ou removidas) até o usuário confirmar via
-- POST /upload/confirm. Evita reenvio e reprocessamento do arquivo.
-- =========================================================

create table pending_imports (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references projects (id) on delete cascade,
    owner_id     uuid not null references auth.users (id),
    created_at   timestamptz not null default now(),
    expires_at   timestamptz not null default (now() + interval '15 minutes'),
    status       text not null default 'pending'
                 check (status in ('pending', 'confirmed', 'expired', 'cancelled')),
    file_url     text,            -- arquivo original já enviado ao Supabase Storage
    diff_summary jsonb not null,  -- contagens p/ exibição: tasks_added, tasks_removed, dependencies_changed...
    payload      jsonb not null   -- tasks/dependencies/progress já parseados, prontos p/ aplicar no confirm
);

create index idx_pending_imports_project_id on pending_imports (project_id);
create index idx_pending_imports_expires_at on pending_imports (expires_at);

alter table pending_imports enable row level security;

create policy pending_imports_owner_access on pending_imports
    for all
    using (owner_id = auth.uid())
    with check (owner_id = auth.uid());
