# Estado Atual do Projeto — 2026-06-30

1. Backend em Python/FastAPI, ambiente validado: Java 17 (Temurin), Python 3.14, venv local em `backend/.venv` (gitignorado).
2. Item 3 concluído: `backend/app/infra/mpxj/` — wrapper MPXJ com `start_jvm()`/`shutdown_jvm()` idempotentes e `read_project_file`/`read_project_bytes` (erro unificado em `MpxjReadError`). Commit `4a78b17`.
3. Item 4 concluído: `backend/app/infra/db/` — pool asyncpg (`pool.py`) e bulk insert via COPY para tasks/dependencies/task_progress + `fetch_task_id_map` (`bulk.py`). Commit `240ab47`.
4. `app/main.py` liga JVM e pool no `lifespan` do FastAPI; `app/core/config.py` lê `DATABASE_URL` via pydantic-settings.
5. Tudo validado contra recursos reais (não mocks): boot da JVM, conexão Postgres do Supabase, COPY real dentro de transação com rollback, app subindo via uvicorn.
6. Migration `003_pending_imports_and_guid.sql` aplicada no Supabase (coluna `ms_project_guid` em `projects` + tabela `pending_imports`). Migrations `001` e `002` já estavam aplicadas.
7. `backend/.env` (gitignorado) tem `DATABASE_URL` configurada com a connection string direta do Supabase (`db.ttqtefwntkgpgatrcyps.supabase.co:5432`).
8. Pendência de segurança: a senha do banco foi colada no chat durante a configuração — recomendado resetá-la no Supabase (Project Settings → Database) antes de produção.
9. Próximo passo (item 5): `backend/app/domain/import_mpp/` — mapear o `org.mpxj.ProjectFile` lido pelo wrapper MPXJ para as tuplas aceitas por `bulk_insert_tasks`/`bulk_insert_dependencies`/`bulk_insert_task_progress`.
10. Nenhuma rota da API (`app/api/v1/`) foi implementada ainda — só a camada de infraestrutura (mpxj + db) está pronta.
