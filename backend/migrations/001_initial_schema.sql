-- Migration: 001_initial_schema
-- Cria a estrutura inicial do banco: projects, tasks, dependencies, snapshots, task_progress
-- Referência: docs/referencia-projeto.md (seção 4)

create extension if not exists pgcrypto;

-- =========================================================
-- ESTRUTURA (quase nunca muda)
-- =========================================================

create table projects (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    created_at  timestamptz not null default now(),
    owner_id    uuid not null references auth.users (id)
);

create table tasks (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references projects (id) on delete cascade,
    ms_uid       integer not null,
    wbs          text,
    name         text not null,
    level        integer,
    type         text,
    duration     numeric,
    is_milestone boolean not null default false,
    constraint tasks_project_ms_uid_unique unique (project_id, ms_uid)
);

create table dependencies (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references projects (id) on delete cascade,
    predecessor_uid integer not null,
    successor_uid   integer not null,
    type            text,
    lag_days        integer not null default 0,
    constraint dependencies_predecessor_fk
        foreign key (project_id, predecessor_uid)
        references tasks (project_id, ms_uid) on delete cascade,
    constraint dependencies_successor_fk
        foreign key (project_id, successor_uid)
        references tasks (project_id, ms_uid) on delete cascade
);

-- =========================================================
-- SNAPSHOTS MENSAIS (só datas e progresso)
-- =========================================================

create table snapshots (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references projects (id) on delete cascade,
    reference_month date not null,
    imported_at     timestamptz not null default now(),
    file_url        text,
    is_baseline     boolean not null default false
);

create table task_progress (
    id               uuid primary key default gen_random_uuid(),
    snapshot_id      uuid not null references snapshots (id) on delete cascade,
    task_id          uuid not null references tasks (id) on delete cascade,
    planned_start    date,
    planned_finish   date,
    forecast_start   date,
    forecast_finish  date,
    actual_start     date,
    actual_finish    date,
    percent_complete numeric(5,2) check (percent_complete between 0 and 100)
);

-- =========================================================
-- ÍNDICES DE PERFORMANCE
-- =========================================================

create index idx_tasks_project_id on tasks (project_id);
create index idx_dependencies_project_id on dependencies (project_id);
create index idx_snapshots_project_id on snapshots (project_id);
create index idx_task_progress_snapshot_id on task_progress (snapshot_id);
create index idx_task_progress_task_id on task_progress (task_id);

-- =========================================================
-- ROW LEVEL SECURITY
-- Isolamento por conta: usuário só acessa dados de projetos onde é owner_id
-- =========================================================

alter table projects enable row level security;
alter table tasks enable row level security;
alter table dependencies enable row level security;
alter table snapshots enable row level security;
alter table task_progress enable row level security;

create policy projects_owner_access on projects
    for all
    using (owner_id = auth.uid())
    with check (owner_id = auth.uid());

create policy tasks_owner_access on tasks
    for all
    using (exists (
        select 1 from projects
        where projects.id = tasks.project_id
          and projects.owner_id = auth.uid()
    ))
    with check (exists (
        select 1 from projects
        where projects.id = tasks.project_id
          and projects.owner_id = auth.uid()
    ));

create policy dependencies_owner_access on dependencies
    for all
    using (exists (
        select 1 from projects
        where projects.id = dependencies.project_id
          and projects.owner_id = auth.uid()
    ))
    with check (exists (
        select 1 from projects
        where projects.id = dependencies.project_id
          and projects.owner_id = auth.uid()
    ));

create policy snapshots_owner_access on snapshots
    for all
    using (exists (
        select 1 from projects
        where projects.id = snapshots.project_id
          and projects.owner_id = auth.uid()
    ))
    with check (exists (
        select 1 from projects
        where projects.id = snapshots.project_id
          and projects.owner_id = auth.uid()
    ));

create policy task_progress_owner_access on task_progress
    for all
    using (exists (
        select 1 from snapshots
        join projects on projects.id = snapshots.project_id
        where snapshots.id = task_progress.snapshot_id
          and projects.owner_id = auth.uid()
    ))
    with check (exists (
        select 1 from snapshots
        join projects on projects.id = snapshots.project_id
        where snapshots.id = task_progress.snapshot_id
          and projects.owner_id = auth.uid()
    ));
