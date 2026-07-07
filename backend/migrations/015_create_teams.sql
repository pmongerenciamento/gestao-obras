-- ============================================================
-- 015_create_teams.sql
-- ROLLBACK:
--   alter table profiles drop column if exists system_role;
--   alter table projects drop column if exists team_id;
--   drop table if exists team_members;
--   drop table if exists teams;
-- ============================================================
create table teams (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_at timestamptz not null default now()
);

create table team_members (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id),
  profile_id uuid not null references profiles(id),
  partner_tier text check (partner_tier in ('founding', 'associate')),
  is_lead boolean not null default false,
  created_at timestamptz not null default now(),
  unique (team_id, profile_id)
);

alter table projects add column team_id uuid references teams(id);
alter table profiles add column system_role text;

insert into teams (name) values ('Diego/Murillo'), ('Carlos'), ('Weslley');
-- Preencher com os profile_id reais depois:
-- insert into team_members (team_id, profile_id, partner_tier)
-- select id, '<uuid-diego>', 'founding' from teams where name = 'Diego/Murillo';
