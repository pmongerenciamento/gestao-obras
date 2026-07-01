# Estado Atual do Projeto — 2026-07-01

1. Backend em Python/FastAPI, ambiente validado: Java 17 (Temurin), Python 3.14, venv local em `backend/.venv` (gitignorado).
2. Item 3 concluído: `backend/app/infra/mpxj/` — wrapper MPXJ com `start_jvm()`/`shutdown_jvm()` idempotentes e `read_project_file`/`read_project_bytes` (erro unificado em `MpxjReadError`). Commit `4a78b17`.
3. Item 4 concluído: `backend/app/infra/db/` — pool asyncpg (`pool.py`) e bulk insert via COPY para tasks/dependencies/task_progress + `fetch_task_id_map` (`bulk.py`). Commit `240ab47`.
4. `app/main.py` liga JVM e pool no `lifespan` do FastAPI; `app/core/config.py` lê `DATABASE_URL` via pydantic-settings.
5. Migration `003_pending_imports_and_guid.sql` aplicada no Supabase (coluna `ms_project_guid` em `projects` + tabela `pending_imports`). Migrations `001` e `002` já estavam aplicadas.
6. `backend/.env` (gitignorado) tem `DATABASE_URL` configurada com a connection string direta do Supabase (`db.ttqtefwntkgpgatrcyps.supabase.co:5432`).
7. Pendência de segurança: a senha do banco foi colada no chat durante a configuração — recomendado resetá-la no Supabase (Project Settings → Database) antes de produção.
8. **Item 5 concluído**: `backend/app/domain/import_mpp/mapping.py` — mapeia `org.mpxj.ProjectFile` para as tuplas de `bulk_insert_tasks`/`bulk_insert_dependencies`/`bulk_insert_task_progress` (`map_tasks`, `map_dependencies`, `map_task_progress`, exportadas em `__init__.py`).
   - Fixture real de teste em `backend/tests/fixtures/sample_project.mpp` (15MB, gitignorado — dado de cliente). 4463 tasks reais, 7138 dependencies.
   - Decisões de mapeamento tomadas nesta etapa (documentadas nos docstrings do módulo):
     - `tasks.type` = `'summary' | 'milestone' | 'task'` (classificação própria, não é o `TaskType` do MPXJ como FIXED_DURATION/FIXED_UNITS/FIXED_WORK — esse é detalhe de cálculo de agenda do MS Project e não interessa ao sistema).
     - Task uid `0` é filtrada — é a "project summary task" sintética do MPXJ, não uma tarefa real.
     - `duration` e `lag_days` são normalizados para dias via `Duration.convertUnits(TimeUnit.DAYS, properties)`, independente da unidade original do arquivo.
     - `planned_start`/`planned_finish` em `map_task_progress` vêm só do Baseline Start/Finish do MS Project, **sem fallback** para Start/Finish atual. No arquivo de teste o baseline estava vazio (era um `.mpp` de exemplo sem baseline salvo), mas o usuário confirmou (2026-07-01): os engenheiros deste time sempre salvam baseline no `.mpp` antes de importar — então na prática esses campos chegam preenchidos, e não é necessário fallback. Decisão final, não mais um "TODO para o item 6".
   - Validado contra o `.mpp` real: tipos Python puros nas tuplas (sem objetos Java residuais), datas convertidas corretamente (`java.time.LocalDateTime` → `date`), encoding UTF-8 correto (acentos como "MÊS" confirmados via leitura de bytes — o `?` que aparece no console é só codepage do terminal, não é um problema nos dados).
   - Validado ponta a ponta contra o Supabase real dentro de uma transação com rollback (nenhum dado persistiu): `bulk_insert_tasks` (4463 linhas, 0.19s) → `fetch_task_id_map` → `bulk_insert_dependencies` (7138 linhas, 0.34s) → `bulk_insert_task_progress` (4463 linhas, 0.18s). Como `auth.users` está vazio (nenhum signup ainda), o teste criou um usuário mínimo só dentro da transação para satisfazer a FK de `projects.owner_id`.
   - Ainda não commitado.
9. Próximo passo (item 6): `backend/app/domain/snapshots/` — decidir tipo de importação (inicial/mensal/mudança estrutural) e orquestrar quando um snapshot é baseline. (Fallback de planned_start/planned_finish não é mais necessário — ver item 8.)
10. Nenhuma rota da API (`app/api/v1/`) foi implementada ainda — só a camada de infraestrutura (mpxj + db) e o mapeamento de domínio (import_mpp) estão prontos.
