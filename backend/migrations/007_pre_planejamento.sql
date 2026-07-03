-- Migration: 007_pre_planejamento
-- Módulo Pré-planejamento: simulador de Linha de Balanço independente do
-- MS Project (roda sem nenhum .mpp importado). Estrutura deliberadamente
-- separada do cronograma real (tasks/dependencies/snapshots/task_progress).
-- Referência: docs/sessao-atual.md (itens 41-48)

-- =========================================================
-- CENÁRIOS (estudos)
-- =========================================================

create table sim_studies (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects (id) on delete cascade,
    name        text not null,
    start_date  date not null,
    created_at  timestamptz not null default now()
);

-- =========================================================
-- SERVIÇOS (colunas da grade) e PAVIMENTOS (linhas da grade)
-- =========================================================

create table sim_services (
    id           uuid primary key default gen_random_uuid(),
    study_id     uuid not null references sim_studies (id) on delete cascade,
    name         text not null,
    color        text not null,
    order_index  integer not null default 0,
    lag_days     integer not null default 0
    -- defasagem (dias úteis) entre pavimentos consecutivos deste serviço,
    -- dentro do mesmo grupo/torre — decisão do usuário, ver plano da sessão.
);

create table sim_floors (
    id           uuid primary key default gen_random_uuid(),
    study_id     uuid not null references sim_studies (id) on delete cascade,
    group_name   text not null,  -- nome da torre/grupo (torres correm em paralelo)
    floor_name   text not null,
    order_index  integer not null default 0
);

-- =========================================================
-- CICLOS (célula da grade: serviço × pavimento) e VÍNCULOS
-- (encadeamento automático entre pavimentos consecutivos do mesmo serviço,
-- gerado a cada save de /ciclos — não editado manualmente no MVP)
-- =========================================================

create table sim_cycles (
    id             uuid primary key default gen_random_uuid(),
    study_id       uuid not null references sim_studies (id) on delete cascade,
    service_id     uuid not null references sim_services (id) on delete cascade,
    floor_id       uuid not null references sim_floors (id) on delete cascade,
    duration_days  integer not null check (duration_days > 0),
    constraint sim_cycles_service_floor_unique unique (service_id, floor_id)
);

create table sim_links (
    id              uuid primary key default gen_random_uuid(),
    study_id        uuid not null references sim_studies (id) on delete cascade,
    predecessor_id  uuid not null references sim_cycles (id) on delete cascade,
    successor_id    uuid not null references sim_cycles (id) on delete cascade,
    lag_days        integer not null default 0
);

-- =========================================================
-- CALENDÁRIO DE FERIADOS (nacionais pré-cadastrados + personalizados)
-- =========================================================

create table sim_holidays (
    id           uuid primary key default gen_random_uuid(),
    study_id     uuid not null references sim_studies (id) on delete cascade,
    date         date not null,
    description  text not null,
    is_national  boolean not null default false,
    constraint sim_holidays_study_date_unique unique (study_id, date)
);

-- =========================================================
-- ÍNDICES
-- =========================================================

create index idx_sim_studies_project_id on sim_studies (project_id);
create index idx_sim_services_study_id on sim_services (study_id);
create index idx_sim_floors_study_id on sim_floors (study_id);
create index idx_sim_cycles_study_id on sim_cycles (study_id);
create index idx_sim_links_study_id on sim_links (study_id);
create index idx_sim_holidays_study_id on sim_holidays (study_id);

-- =========================================================
-- ROW LEVEL SECURITY
-- Mesmo padrão de tasks/dependencies (001) — dono via projects.owner_id.
-- Não protege o caminho do backend (DATABASE_URL direto, ignora RLS — nota
-- do item 30 de docs/sessao-atual.md), mas mantém consistência caso algo
-- mais acesse direto no futuro.
-- =========================================================

alter table sim_studies enable row level security;
alter table sim_services enable row level security;
alter table sim_floors enable row level security;
alter table sim_cycles enable row level security;
alter table sim_links enable row level security;
alter table sim_holidays enable row level security;

create policy sim_studies_owner_access on sim_studies
    for all
    using (exists (
        select 1 from projects
        where projects.id = sim_studies.project_id
          and projects.owner_id = auth.uid()
    ))
    with check (exists (
        select 1 from projects
        where projects.id = sim_studies.project_id
          and projects.owner_id = auth.uid()
    ));

create policy sim_services_owner_access on sim_services
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_services.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_services.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));

create policy sim_floors_owner_access on sim_floors
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_floors.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_floors.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));

create policy sim_cycles_owner_access on sim_cycles
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_cycles.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_cycles.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));

create policy sim_links_owner_access on sim_links
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_links.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_links.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));

create policy sim_holidays_owner_access on sim_holidays
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_holidays.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_holidays.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));
