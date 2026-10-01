-- ============================================================
-- 016_clients_rls.sql
-- Habilita RLS em `clients` (011_create_clients.sql não tinha nenhuma —
-- gap encontrado ao ligar o frontend direto na tabela, docs/sessao-atual.md).
-- Sem owner_id (cadastro compartilhado por toda a equipe, não por usuário),
-- então a policy só exige sessão autenticada, sem corte por dono.
-- Nota: CREATE POLICY não aceita múltiplos comandos num único `for`
-- (`for insert, update, delete` não é sintaxe válida) — a escrita fica numa
-- única policy `for all`, que também cobre select (redundante com a policy
-- de leitura abaixo, mas inofensivo: Postgres libera se qualquer policy
-- aplicável permitir).
-- ROLLBACK:
--   drop policy if exists clients_select_authenticated on clients;
--   drop policy if exists clients_write_authenticated on clients;
--   alter table clients disable row level security;
-- ============================================================

alter table clients enable row level security;

create policy clients_select_authenticated on clients
  for select
  to authenticated
  using (true);

create policy clients_write_authenticated on clients
  for all
  to authenticated
  using (true)
  with check (true);
