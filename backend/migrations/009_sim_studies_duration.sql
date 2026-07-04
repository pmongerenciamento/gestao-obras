-- Migration: 009_sim_studies_duration
-- Prazo estimado (em meses) do cenário, usado para calcular e exibir o
-- término esperado no banner da aba Calendário. Nullable pra não quebrar
-- cenários criados antes desta migration (sem esse dado).

alter table sim_studies add column duration_months integer;
