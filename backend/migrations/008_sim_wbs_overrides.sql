-- Migration: 008_sim_wbs_overrides
-- Predecessores editados pelo planejador na aba "Estrutura WBS" — cada linha
-- é um par (tarefa, predecessora), várias linhas por tarefa = vários
-- predecessores. Separado de sim_links (que continua existindo, mas deixa
-- de ser gerado automaticamente pelo save da grade — ver domain/pre_planejamento).
-- Referência: docs/sessao-atual.md — módulo Pré-planejamento, aba Estrutura WBS

create table sim_wbs_overrides (
    id              uuid primary key default gen_random_uuid(),
    study_id        uuid not null references sim_studies (id) on delete cascade,
    cycle_id        uuid not null references sim_cycles (id) on delete cascade,
    predecessor_id  uuid not null references sim_cycles (id) on delete cascade,
    constraint sim_wbs_overrides_unique unique (cycle_id, predecessor_id)
);

create index idx_sim_wbs_overrides_study_id on sim_wbs_overrides (study_id);
create index idx_sim_wbs_overrides_cycle_id on sim_wbs_overrides (cycle_id);

alter table sim_wbs_overrides enable row level security;

create policy sim_wbs_overrides_owner_access on sim_wbs_overrides
    for all
    using (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_wbs_overrides.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ))
    with check (exists (
        select 1 from sim_studies
        where sim_studies.id = sim_wbs_overrides.study_id
          and exists (
              select 1 from projects
              where projects.id = sim_studies.project_id
                and projects.owner_id = auth.uid()
          )
    ));
