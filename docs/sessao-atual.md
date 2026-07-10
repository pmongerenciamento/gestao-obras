# Estado Atual do Projeto — 2026-07-02

1. Backend em Python/FastAPI, ambiente validado: Java 17 (Temurin), Python 3.14, venv local em `backend/.venv` (gitignorado).
   - **Ambiente de desenvolvimento**: o usuário roda o Claude Code via **CMD do Windows**, não pelo terminal integrado do VS Code — relevante para instruções/comandos sugeridos em sessões futuras (o usuário abre um CMD à parte, não a aba de terminal dentro do VS Code).
2. Item 3 concluído: `backend/app/infra/mpxj/` — wrapper MPXJ com `start_jvm()`/`shutdown_jvm()` idempotentes e `read_project_file`/`read_project_bytes` (erro unificado em `MpxjReadError`). Commit `4a78b17`.
3. Item 4 concluído: `backend/app/infra/db/` — pool asyncpg (`pool.py`) e bulk insert via COPY para tasks/dependencies/task_progress + `fetch_task_id_map` (`bulk.py`). Commit `240ab47`.
4. `app/main.py` liga JVM e pool no `lifespan` do FastAPI; `app/core/config.py` lê `DATABASE_URL` via pydantic-settings.
5. Migration `003_pending_imports_and_guid.sql` aplicada no Supabase (coluna `ms_project_guid` em `projects` + tabela `pending_imports`). Migrations `001` e `002` já estavam aplicadas.
6. `backend/.env` (gitignorado) tem `DATABASE_URL` configurada com a connection string direta do Supabase (`db.ttqtefwntkgpgatrcyps.supabase.co:5432`).
7. Pendência de segurança: a senha do banco foi colada no chat durante a configuração — recomendado resetá-la no Supabase (Project Settings → Database) antes de produção. **Atualização 2026-07-01**: `SUPABASE_SERVICE_ROLE_KEY` e `SUPABASE_SECRET_KEY` também apareceram em texto puro no chat (li o `.env` inteiro pra conferir a config existente) — rotacionar essas também antes de produção (Project Settings → API).
8. **Item 5 concluído** (commit `6b30262`): `backend/app/domain/import_mpp/mapping.py` — mapeia `org.mpxj.ProjectFile` para as tuplas de `bulk_insert_tasks`/`bulk_insert_dependencies`/`bulk_insert_task_progress` (`map_tasks`, `map_dependencies`, `map_task_progress`, exportadas em `__init__.py`).
   - Fixture real de teste em `backend/tests/fixtures/sample_project.mpp` (15MB, gitignorado — dado de cliente). 4463 tasks reais, 7138 dependencies.
   - Decisões de mapeamento (documentadas nos docstrings do módulo):
     - `tasks.type` = `'summary' | 'milestone' | 'task'` (classificação própria, não é o `TaskType` do MPXJ como FIXED_DURATION/FIXED_UNITS/FIXED_WORK — esse é detalhe de cálculo de agenda do MS Project e não interessa ao sistema).
     - Task uid `0` é filtrada — é a "project summary task" sintética do MPXJ, não uma tarefa real.
     - `duration` e `lag_days` são normalizados para dias via `Duration.convertUnits(TimeUnit.DAYS, properties)`, independente da unidade original do arquivo.
     - `planned_start`/`planned_finish` vêm só do Baseline Start/Finish do MS Project, **sem fallback** — confirmado pelo usuário (2026-07-01): os engenheiros deste time sempre salvam baseline antes de importar.
   - Validado contra o `.mpp` real (tipos Python puros, datas convertidas corretamente, encoding UTF-8 ok — "MÊS" com acento confirmado por bytes, o `?` no console é só codepage do terminal) e ponta a ponta contra o Supabase real dentro de transação com rollback.
9. **Item 6 concluído**: `backend/app/domain/snapshots/snapshots.py` — `process_import(conn, owner_id, project, fallback_name, reference_month, file_url=None) -> ImportResult`, ponto de entrada único que decide `ImportType.INITIAL | MONTHLY_UPDATE | STRUCTURAL_CHANGE`:
   - **INITIAL** (projeto novo, identificado por `ms_project_guid` — `ProjectProperties.getGUID()`, estável mesmo se o nome mudar): cria `projects`, `bulk_insert_tasks`, `bulk_insert_dependencies`, snapshot com `is_baseline=true`, `bulk_insert_task_progress`.
   - **MONTHLY_UPDATE** (projeto existe, conjunto de `ms_uid`/dependencies idêntico ao banco): só cria snapshot novo (`is_baseline=false`) + `task_progress` — `tasks`/`dependencies` não são reinseridas.
   - **STRUCTURAL_CHANGE** (tasks ou dependencies novas/removidas): não aplica nada em `tasks`/`dependencies`/`snapshots` — grava `diff_summary` (contagens: tasks_added/removed, dependencies_added/removed) + `payload` (tasks/dependencies/progresso já mapeados, progresso chaveado por `ms_uid` já que tasks novas ainda não têm `id`) em `pending_imports`, status `pending`.
   - Suporte novo em `domain/import_mpp/mapping.py`: `get_project_guid`, `get_project_name` (fallback para nome do arquivo — `ProjectProperties.getName()` veio `None` no arquivo real de teste, comum quando o usuário nunca preenche File → Info → Properties), `map_task_progress_by_ms_uid` (`map_task_progress` agora é implementada em cima dela).
   - **Decisão pendente de implementação, já resolvida em conversa**: quando uma mudança estrutural for confirmada (item futuro — `POST /upload/confirm`, ainda não existe), task removida vai virar **soft-delete** (nova coluna tipo `removed_at`, precisa migration nova), não `DELETE` — porque `task_progress` tem `ON DELETE CASCADE` de `tasks` e apagar a task destruiria o histórico de progresso dela em todos os snapshots antigos. Decisão do usuário em 2026-07-01, alinhada com o diferencial do produto ("arquivo original preservado com histórico auditável").
   - Validado com 3 chamadas sequenciais de `process_import` contra o `.mpp` real, dentro de uma transação com rollback no Supabase real: 1ª → INITIAL (4463 tasks, 7138 deps, is_baseline=true); 2ª (mesmo arquivo) → MONTHLY_UPDATE (não duplicou tasks/deps, snapshot novo com is_baseline=false); 3ª (uma task+dependency removida manualmente do banco pra simular divergência) → STRUCTURAL_CHANGE com diff_summary correto e payload JSON válido/reidratável em `pending_imports`, sem tocar tasks/dependencies/snapshots. Rollback confirmado limpo (contagem zero em todas as tabelas depois).
   - Plano completo em `C:\Users\pmon_admin\.claude\plans\ticklish-launching-pascal.md`.
   - Commit `31503c0`.
10. **Item 7 concluído — backend completo até aqui**: `POST /api/v1/upload` (`backend/app/api/v1/routes_import.py`), primeira rota HTTP real do projeto. Recebe o `.mpp` via multipart, valida com `read_project_bytes` (400 se `MpxjReadError`), sobe o arquivo original pro Supabase Storage, chama `process_import` dentro de `async with conn.transaction():`, devolve 201 (inicial/atualização) ou 202 (mudança estrutural pendente).
    - **Auth**: `core/security.py::verify_token` valida o access token do Supabase Auth via `client.auth.get_user(token)`; `core/dependencies.py` expõe `get_current_user` (extrai `owner_id` do JWT, via `HTTPBearer`) e `get_db` (conexão do pool via `Depends`). Sem token → 401.
    - **Nota de arquitetura importante**: o backend conecta no Postgres via `DATABASE_URL` direto (role `postgres`), não via PostgREST — `auth.uid()` nunca é setado, então as políticas RLS das migrations `001`/`003` não protegem nada nesse caminho. Quem garante isolamento por conta é o próprio código (`process_import` já filtra tudo por `owner_id`). RLS só importa se algo além do backend acessar o banco diretamente no futuro.
    - **Storage**: `infra/storage/client.py` (cliente Supabase assíncrono compartilhado, iniciado/encerrado no `lifespan`, mesmo padrão do pool asyncpg) + `infra/storage/storage.py::upload_original_file` (sobe pro bucket privado `mpp-files`, caminho `{owner_id}/{uuid4()}-{nome do arquivo}`, devolve a storage key — não uma URL pública, o bucket é privado).
    - **Setup feito nesta sessão**: `pip install supabase==2.31.0` no venv (estava no `requirements.txt` mas nunca tinha sido instalado — trouxe `gotrue`/`storage3`/`postgrest`/`realtime` como dependências); bucket `mpp-files` criado no Supabase Storage (privado).
    - **Bug encontrado e corrigido durante a validação ao vivo**: `process_import` recebia `file_url` mas nunca gravava — o INSERT em `snapshots` não incluía a coluna `file_url`. Corrigido em `_apply_initial_import`/`_apply_monthly_update` (`domain/snapshots/snapshots.py`).
    - **Validado de ponta a ponta com servidor real** (não dava pra usar transação com rollback aqui — a chamada passa pelo pool do próprio app rodando via `uvicorn`, não por uma conexão controlada por fora): subiu `uvicorn` local, criou um usuário de teste real no Supabase Auth (Admin API), testou sem `Authorization` (401), arquivo inválido (400), upload real do `sample_project.mpp` (201 `initial`, 4463 tasks/7138 deps/`is_baseline=true`), reenvio do mesmo arquivo (201 `monthly_update`, sem duplicar estrutura), confirmou os 2 arquivos originais de fato no bucket (download + conferência de tamanho). Limpou tudo depois (projeto via cascade, objetos no bucket, usuário de teste) — apagar o projeto de teste exigiu desabilitar temporariamente o trigger de imutabilidade do baseline (`trg_prevent_baseline_modification`), reabilitado logo em seguida; isso é o trigger funcionando corretamente (só bloqueia por padrão, não é bug).
    - Plano completo em `C:\Users\pmon_admin\.claude\plans\ticklish-launching-pascal.md`.
    - Commit `92e562b`.
11. **Fora de escopo, registrado pra depois**: `POST /upload/confirm` (aplicar mudança estrutural pendente — precisa da migration de soft-delete descrita no item 9).
12. **Backend 100% concluído** (confirmado pelo usuário em 2026-07-01: item 7 era o último item do backend antes do frontend). Todos os commits do backend desta sessão: `4a78b17`, `240ab47`, `6b30262`, `31503c0`, `92e562b`.
13. **Pendências de segurança antes de produção** (nenhuma bloqueia o desenvolvimento, mas precisam ser feitas antes de ir pra produção): resetar a senha do banco (`DATABASE_URL`) e rotacionar `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_SECRET_KEY` — todas apareceram em texto puro no chat em algum momento desta sessão (Project Settings → Database / → API no painel do Supabase).
14. **Pendência para a próxima sessão**: o usuário precisa providenciar o **logo PMON** (PNG ou SVG) — necessário para a tela de login e a sidebar do frontend (`frontend/public/logo/`, já reservado na estrutura de pastas do `docs/referencia-projeto.md`).
15. **Frontend ainda não iniciado** (situação no fim da sessão de 2026-07-01): a pasta `frontend/` existia com a estrutura de pastas esqueleto e um `package.json` mínimo sem dependências — `npm install` nunca tinha sido rodado, nenhum código escrito.

## Sessão 2026-07-02 — Frontend: scaffold + tela de login

16. Logo PMON adicionado pelo usuário em `frontend/public/logo/LOGO_PMON.png`.
17. **Scaffold do Next.js montado manualmente** (sem `create-next-app`, pra não sobrescrever a estrutura de pastas já reservada em `docs/referencia-projeto.md`): `package.json` (Next 15 + React 19 + TypeScript + Tailwind 3 + `@supabase/supabase-js`/`@supabase/ssr` + `d3`), `tsconfig.json`, `next.config.ts`, `tailwind.config.ts` (tokens `pmon.black #0D0D0D` / `pmon.yellow #F5C400` / `pmon.white`), `postcss.config.mjs`, `eslint.config.mjs` (flat config, ignora `.next/**` e `next-env.d.ts` — sem isso o lint rodava em cima do build gerado). `npm install` executado com sucesso (436 pacotes). 2 vulnerabilidades moderadas (XSS no `postcss` transitivo do Next 15.5.20) — não corrigidas, o fix automático faria downgrade quebrado pro Next 9.
18. **Tela de login implementada** (plano completo em `C:\Users\pmon_admin\.claude\plans\adaptive-crafting-popcorn.md`):
    - `lib/supabase/client.ts` / `server.ts`: `createBrowserClient`/`createServerClient` via `@supabase/ssr`, usando `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (formato novo `sb_publishable_...`) em vez da `NEXT_PUBLIC_SUPABASE_ANON_KEY` legada — decisão do usuário, ambas as chaves existem no `.env.local`.
    - `middleware.ts` (raiz de `frontend/`, não estava na estrutura original do `docs/referencia-projeto.md` — peça necessária pra separação `(auth)`/`(app)` funcionar): sem sessão fora de `/login` → redireciona pra `/login`; com sessão em `/login` → redireciona pra `/`.
    - `components/ui/Button.tsx` e `Input.tsx`: primitivos reutilizáveis com tema PMON (primeira peça da pasta `components/ui/` reservada na estrutura do projeto).
    - `components/auth/LoginForm.tsx` (pasta nova, não prevista na estrutura original): Client Component, chama `supabase.auth.signInWithPassword`.
    - `app/(auth)/login/page.tsx`: stub substituído pela tela real (logo + form, fundo `pmon-black`).
    - "Esqueceu a senha?" fica como placeholder visual (decisão do usuário) — sem fluxo funcional ainda.
19. **Bug encontrado durante o teste real com o usuário**: `app/(app)/layout.tsx` e `app/(app)/page.tsx` eram stubs sem `export default` → após login bem-sucedido (redirect pra `/`), o Next quebrava com `"The default export is not a React Component"`. Corrigido com stub mínimo — decisão do usuário foi ir com stub mínimo agora em vez de planejar o painel completo nesta etapa:
    - `(app)/layout.tsx`: só renderiza `{children}` num `div` com fundo `pmon-black`.
    - `(app)/page.tsx`: texto placeholder "Painel principal — em construção."
    - `Sidebar.tsx`/`Header.tsx` (`components/layout/`) continuam stub — Sidebar/Header/cards de projeto ficam pra uma próxima etapa planejada.
    - **Nota**: `app/(app)/projetos/[projectId]/*` (6 páginas + layout) continuam stub sem `export default` — só vão quebrar quando alguém navegar pra dentro de um projeto específico; ainda não acontece nesta etapa.
20. **Validado com usuário de teste real e persistente** no Supabase Auth (`diego@pmongerenciamento.com.br`, criado pelo próprio usuário no painel do Supabase — diferente do usuário efêmero criado/apagado dentro de transação na sessão de validação do backend). Usuário testou visualmente no navegador: login com credenciais reais funcionou, redirecionamento pra `/` confirmado, middleware protegendo a área autenticada confirmado.
21. Commit `e2af5ce`: "Implementa tela de login PMON: autenticação Supabase, middleware de proteção de rotas e identidade visual (preto/amarelo/branco)".
22. **Próximo passo sugerido**: implementar o painel principal de verdade (`Sidebar`, `Header` com logout, cards de projeto + "+ Novo Projeto"), depois o módulo de importação no frontend (tela de upload consumindo `POST /api/v1/upload`, já pronto no backend).

## Sessão 2026-07-02 (continuação) — Painel de projetos + tela interna do projeto

23. **Painel de projetos implementado** (mockup aprovado): `app/(app)/page.tsx` vira Server Component real — tema claro (`pmon.bg #F4F4F4`, novo token no `tailwind.config.ts`), grid 3 colunas de `components/layout/ProjectCard.tsx` (imagem do empreendimento, cliente, nome, cidade com ícone de local, badge de status, avatares dos membros pequenos e sobrepostos, borda que fica amarela no hover), botão "Novo projeto" (placeholder, sem ação ainda), subtítulo "X projetos ativos" no `Header.tsx` (ganhou prop `subtitle`), `components/layout/AdminBar.tsx` fixa no rodapé da viewport, só pra usuário master.
24. **"Usuário master" mockado**: `lib/auth/roles.ts::isMasterUser` — backend não tem esse conceito ainda (só `owner_id` por projeto, sem role nem tabela de membros) — lista fixa de e-mails no código (`diego@pmongerenciamento.com.br`), comparação case-insensitive. **Bug encontrado e corrigido**: a primeira versão comparava e-mail com case-sensitivity exata, então a barra de admin não aparecia mesmo pro e-mail certo.
25. **Tela interna do projeto implementada**: `app/(app)/projetos/[projectId]/layout.tsx` (antes era stub quebrado sem `export default`) agora busca o projeto mockado e renderiza `Header.tsx` (breadcrumb "Projetos › {nome}") + `components/layout/ProjectSidebar.tsx` (220px, clara — **substitui** o stub `ProjectTabs.tsx`, removido: o mockup usa sidebar de navegação, não abas). Sidebar mostra imagem/cliente/nome/cidade/badge do último snapshot (fundo amarelo claro, borda amarela sutil) e nav dos 7 módulos com ícone Tabler cada (`IconHome`, `IconUpload`, `IconChartLine`, `IconLayoutBoard`, `IconTruck`, `IconColumns`, `IconFileAnalytics`) e indicador de borda esquerda amarela no item ativo. `app/(app)/projetos/[projectId]/page.tsx` (não existia — arquivo novo) é a "Visão geral": 4 cards de data com ícone (início do projeto, término linha de base, término projetado, última importação) + grid de cards de módulo com ícone e descrição curta cada. Os 6 módulos (`importacao`, `linha-de-balanco`, `gestao-a-vista`, `suprimentos`, `kanban`, `relatorios`) ganharam placeholder mínimo ("em construção") pra não quebrar a navegação ao clicar.
26. **Nova dependência**: `@tabler/icons-react` — os 12 nomes de ícone usados foram conferidos manualmente contra o `.d.ts` do pacote antes de usar (todos existem: `IconHome`, `IconUpload`, `IconChartLine`, `IconLayoutBoard`, `IconTruck`, `IconColumns`, `IconFileAnalytics`, `IconMapPin`, `IconCalendarEvent`, `IconFlag3`, `IconCalendarStats`, `IconHistory`). Lista de módulos centralizada em `lib/project-modules.ts` (ícone + descrição por módulo), reusada pela sidebar e pelo grid da Visão geral.
27. **Bug de proporção do logo corrigido**: `LOGO_PMON.png` é uma imagem quadrada (2565×2565px, confirmado lendo o header do PNG) — `app/(auth)/login/page.tsx` usava `width={160} height={64}` (proporção errada, 2.5:1), causando distorção visual do logo na tela de login *e* um warning do `<Image>` do Next.js no console do navegador (aparecia como badge "1 Issue" no overlay de dev). Corrigido pra `width={64} height={64}`. O logo do `Header.tsx` já estava correto (`32×32`, proporção 1:1).
28. **Reportado pelo usuário**: um warning de hydration (`hidden={true}` vs `hidden={null}`) num elemento com `id="ptt_birro"` apareceu no console durante o desenvolvimento. Esse `id` não existe em nenhum componente deste projeto — o diagnóstico mais provável é uma extensão de browser injetando atributos no DOM antes do React hidratar (padrão comum desse tipo de warning). Não foi possível verificar diretamente nesta sessão (sem acesso ao console do navegador do usuário a partir do ambiente onde o Claude Code roda). Pode aparecer em ambientes com extensões instaladas e geralmente é seguro ignorar durante o desenvolvimento — se persistir numa aba anônima/sem extensões, vale investigar de novo.
29. **Dados dos projetos ainda mockados**: `lib/api/projects.ts` (`listProjects`/`getProject`) retorna um array fixo em memória — o backend não tem `GET /api/v1/projects` (`routes_projects.py` ainda é stub) nem colunas de cliente/cidade/imagem/status na tabela `projects`, nem conceito de múltiplos usuários por projeto. A troca pro endpoint real fica isolada a este arquivo (assinatura já é `async`, resto do app já está escrito contra ela).
30. Commit `2678660`: "Implementa painel de projetos e tela interna: cards, sidebar, módulos, refinamento visual PMON e correção de proporção do logo".
31. **Próximos passos**: formulário de cadastro de novo projeto (hoje o botão "Novo projeto" é placeholder), tela de gestão de usuários (hoje link placeholder na `AdminBar`), e conectar o frontend ao backend de verdade — começando por `GET /api/v1/projects` pra tirar os dados mockados de `lib/api/projects.ts`.

## Sessão 2026-07-02 (continuação 2) — Cadastro real de projeto + exclusão

32. **Migration `004_project_fields.sql`** criada e aplicada no Supabase real: 16 colunas novas em `projects` (client_name, city, state, tipologia_obra, tipologia_construtiva[_outros], num_torres/pavimentos/unidades/lotes, area_construida/area_privativa, orcamento, data_base_orcamento, prazo_estimado_meses, image_url). Nenhuma `NOT NULL` no banco — `ALTER TABLE ADD COLUMN NOT NULL` sem `DEFAULT` falharia numa tabela com linhas, e obrigatoriedade virou regra de aplicação (validação `zod` no formulário), não constraint de banco.
    - **Aplicação exigiu várias rodadas**: o ambiente sandboxed onde o Claude Code roda só tem saída de rede via HTTPS (443) — confirmado que a Storage API do Supabase responde normal, mas a porta direta do Postgres (5432) não é alcançável daqui (timeout de conexão, não é problema de credencial). O usuário rodou o SQL manualmente no SQL Editor do Supabase; uma tentativa truncou/corrompeu especificamente as duas colunas com `CHECK ... IN (...)` (suspeita: autocorreção de aspas do navegador ao colar), resolvido rodando essas duas de novo. Verificação de "a coluna existe" feita via PostgREST por HTTPS (não dava pra usar `psql`/`asyncpg` direto).
33. **Decisão de arquitetura**: cadastro de projeto grava **direto do frontend no Supabase** (browser client + RLS de `owner_id = auth.uid()`, já configurada na migration `001`) — sem endpoint novo no backend, `routes_projects.py` continua stub. `lib/api/projects.ts` (`listProjects`/`getProject`) trocou de mock pra leitura real via `lib/supabase/server.ts` (RLS via cookie de sessão) — os 4 projetos mockados saíram, painel mostra estado vazio até o usuário cadastrar o primeiro projeto de verdade.
    - Gap conhecido: projeto real não tem `status` nem tabela de membros no banco — `listProjects`/`getProject` usam defaults (status sempre `"em_andamento"`, membros = só o dono) até o backend ter esses conceitos de verdade.
34. **Formulário `/projetos/novo` implementado** (`components/projects/NewProjectForm.tsx`, novas dependências `react-hook-form` + `zod` + `@hookform/resolvers`): campos condicionais por tipologia — torres/pavimentos/unidades só pra vertical, número de lotes só pra loteamento (decisão do usuário: área construída/privativa aparecem sempre, não são condicionais); campo "Outros" da tipologia construtiva só aparece quando selecionado; upload de imagem com preview local antes de salvar.
35. **Setup live no Supabase**: bucket `project-images` criado via client Python (`acreate_client` + service role key, por HTTPS — funciona mesmo sem acesso à porta do Postgres) com `public: True`; policies de `storage.objects` (insert/update restritos ao dono via `(storage.foldername(name))[1] = auth.uid()::text`, select público) aplicadas pelo usuário no SQL Editor.
36. `next.config.ts`: `images.remotePatterns` liberando `ttqtefwntkgpgatrcyps.supabase.co/storage/v1/object/public/**` pro `next/image` exibir as imagens reais vindas do Storage.
37. **Formatação de números no formulário**: área construída/privativa e orçamento usam máscara visual pt-BR (`lib/format-number.ts`) via `Controller` do react-hook-form — o campo mostra `"32.000"` / `"R$ 120.000.000,00"` enquanto o usuário digita, mas o valor enviado ao Supabase continua numérico puro. Área ficou limitada a valores inteiros (a máscara só extrai dígitos, sem separador decimal) — bate com o exemplo que o usuário deu.
38. **Exclusão de projeto implementada** (só usuário master, `isMasterUser`): menu de três pontos no canto superior esquerdo do `ProjectCard` (virou Client Component) → dropdown "Excluir projeto" → `components/ui/ConfirmDialog.tsx` (novo, genérico — pensado pra reusar em futuras confirmações destrutivas, não é específico de projeto). Confirmar chama `deleteProject()` (agora em `lib/api/project-mutations.ts`, renomeado de `create-project.ts` já que passou a ter create *e* delete) → `DELETE FROM projects WHERE id = ?`, `CASCADE` cuida de tasks/dependencies/snapshots/task_progress.
    - **Achado importante, ainda não resolvido**: `trg_prevent_baseline_modification` (migration `002`) bloqueia UPDATE/DELETE em `snapshots` com `is_baseline=true` — excluir um projeto **já importado** (com baseline) vai falhar com erro do Postgres propagado pro modal (não crasha a UI, mas também não apaga). Hoje isso não trava nada porque nenhum projeto real ainda tem baseline (importação não está ligada ao frontend). "Excluir projeto importado" fica como decisão de produto separada pra quando o módulo de importação existir no frontend — não contornei o trigger de propósito, ele é o diferencial de imutabilidade do baseline documentado no produto.
    - Reestruturação do card: o `<Link>` que envolvia o card inteiro virou uma camada invisível (`<Link className="absolute inset-0 z-10">`) por trás, com o botão de três pontos em `z-20` por cima — evita `<button>` aninhado dentro de `<a>` (HTML inválido) e mantém "clicar em qualquer lugar do card navega".
    - Imagem do Storage não é apagada junto com o projeto (`CASCADE` só cobre FK do Postgres, não objetos do Storage) — fica órfã no bucket `project-images`. Não implementado, fora do pedido original, registrado como gap.
39. Commits desta continuação: `e68b270` (formulário de cadastro), `63e1a99` (altura do preview alinhada ao card), `a654628` (domínio de imagem + formatação de números), `731b9d4` (exclusão de projeto).
40. **Próximos passos**: tela de gestão de usuários (hoje link placeholder na `AdminBar`), módulo de importação no frontend (`POST /api/v1/upload` já pronto no backend, ainda sem UI), e eventualmente considerar `POST/GET/PATCH /api/v1/projects` no backend pra padronizar a escrita — hoje é 100% frontend-direto-Supabase, decisão válida por enquanto mas vale revisitar se o projeto crescer.

## Sessão 2026-07-02 (continuação 3) — Módulo Pré-planejamento (aprovado, ainda não implementado)

41. **Novo módulo aprovado: "Pré-planejamento"** — simulador de Linha de Balanço independente do MS Project, pra uso em reuniões de concepção com o cliente antes de existir um cronograma definido (ou seja, roda sem precisar de nenhum `.mpp` importado).
42. **Estrutura de dados**: múltiplos cenários por projeto (ex.: Cenário A, Cenário B), cada cenário com sua própria tabela de ciclos (serviços × pavimentos), vínculos entre ciclos com defasagem, feriados e uma data de início do cenário.
43. **Tabela de input**: coluna "Pavimento" fixa (sticky) na lateral, serviços rolam horizontalmente — precisa suportar em torno de 50 serviços.
44. **Visualização de Linha de Balanço do simulador**: cabeçalho em 3 níveis (mês / intervalo semanal / letras dos dias), uma coluna por dia, fins de semana e feriados destacados em cinza, sub-linhas dinâmicas por pavimento (só expande quando há sobreposição de ciclos no mesmo pavimento), sub-linha fixa por serviço, clique numa barra abre modal de edição (permite editar um ciclo único ou a cadeia inteira vinculada).
45. **Schema de banco planejado** (ainda não escrito como migration): tabelas novas `sim_studies`, `sim_services`, `sim_floors`, `sim_cycles`, `sim_links`, `sim_holidays` — deliberadamente separadas das tabelas de cronograma real do MS Project (`tasks`/`dependencies`/`snapshots`/`task_progress`), já que o Pré-planejamento é um simulador independente, não um cronograma importado.
46. **Localização na navegação**: nova seção "Pré-planejamento" na sidebar do projeto (`components/layout/ProjectSidebar.tsx` e `lib/project-modules.ts`), entre "Importar cronograma" e "Linha de balanço".
47. **Nada disso foi implementado ainda** — é só a decisão de escopo/design registrada nesta sessão. Nenhuma migration, tabela, rota ou componente criado. Fica pra planejar em detalhe (com o fluxo de `EnterPlanMode` de sempre) numa sessão futura, junto com o restante do próximo passo já registrado no item 40 (gestão de usuários, módulo de importação).
48. **Calendário de feriados**:
    - O calendário fica **salvo no cenário permanentemente** — não é descartado após gerar a linha de balanço.
    - O planejador pode voltar e revisar/editar o calendário de feriados a qualquer momento, mesmo após a linha de balanço já ter sido gerada.
    - Ao editar o calendário, o sistema deve **recalcular automaticamente** as datas da linha de balanço.

## Sessão 2026-07-03 — Gestão de usuários (implementado)

49. **Tela de gestão de usuários implementada** (link "Gerenciar usuários" da `AdminBar`, antes placeholder, agora real): master cadastra usuários (convite por e-mail), concede/revoga acesso por projeto, bloqueia/desbloqueia conta inteira, reseta senha e exclui usuário. Plano completo aprovado via `EnterPlanMode` antes de codar.
50. **Migrations novas**:
    - `005_users_and_members.sql`: tabela `profiles` (id = `auth.users.id`, full_name, avatar_url) com trigger `trg_on_auth_user_created` (`security definer` — **obrigatório**, sem isso o INSERT em `auth.users` pelo GoTrue quebra com "Database error saving new user", já que o papel interno do GoTrue não tem grant/RLS pra escrever em `public.profiles` por conta própria) que auto-cria a linha de profile pra todo usuário novo; tabela `project_members` (project_id, user_id, invited_by, status `pending|active|blocked`). RLS: leitura de `profiles` liberada pra autenticados, `project_members` só enxerga os próprios vínculos — a gestão de verdade passa pelo backend via `DATABASE_URL` direto (ignora RLS, mesma nota do item 30).
    - `006_avatar_images_storage_policies.sql`: policies de `storage.objects` pro bucket `avatar-images` (insert/update restrito ao dono via `(storage.foldername(name))[1] = auth.uid()::text`, select público) — mesmo padrão do `project-images`, mas dessa vez registrado em migration (antes não tinha ficado, gap corrigido).
51. **Backend**: `core/roles.py` (`MASTER_EMAILS` espelhando `frontend/lib/auth/roles.ts` — decisão do usuário: espelhar lista hardcoded agora, sistema de roles de verdade fica pra depois). `core/security.py`/`dependencies.py` refatorados: `verify_token` devolve `AuthenticatedUser(id, email)` em vez de só `UUID`; `get_current_user` (usado por `routes_import.py`) continua igual por fora; novo `get_current_master_user` valida e-mail contra `is_master`, 403 se não for. `domain/users/users.py`: lista via SQL direto (`auth.users` é tabela Postgres comum, join com `profiles`/`project_members`/`projects` — evita depender de paginação da Admin API só pra listar); escrita usa Admin API do Supabase (`invite_user_by_email`, `update_user_by_id` com `ban_duration` pra bloqueio de conta inteira, `delete_user`, `reset_password_for_email` — não é `generate_link`, que só gera o link e não manda e-mail). `routes_users.py`: `GET/POST/PATCH/DELETE /api/v1/users`, todas atrás de `get_current_master_user`. Ação do PATCH ganhou 2 valores além do planejado original (`block/unblock/reset_password`): `grant` (conceder acesso a um projeto novo pra usuário já existente) e `set_avatar` (salvar `avatar_url` em profiles) — necessários pro `AccessModal` funcionar de ponta a ponta.
    - **Decisões de semântica de bloqueio validadas com o usuário antes de codar**: "Bloquear conta" (sem `project_id`) bane a conta inteira no Supabase Auth; "Revogar acesso" (com `project_id`, dentro do `AccessModal`) só muda `project_members.status` daquele vínculo.
    - **Bug real encontrado e corrigido durante validação ao vivo**: erros do Supabase Auth (e-mail inválido, rate limit) viravam 500 genérico — `routes_users.py` agora captura `AuthError` e repassa o `status`/mensagem originais.
52. **Bucket `avatar-images`** criado (público) via Admin API, com confirmação separada do usuário antes de cada ação live (criação de usuários de teste, criação de projeto de teste, criação do bucket) — seguindo a regra da sessão de pedir autorização por ação, não só uma vez no início.
53. **Frontend**: primeira vez que o frontend chama o backend FastAPI direto (até aqui tudo era frontend-direto-Supabase) — `lib/api/backend-client.ts` (fetch autenticado com o access token da sessão Supabase), `lib/api/users.ts` (leitura server-side) / `user-mutations.ts` (escrita client-side, mesmo padrão de separação de `projects.ts`/`project-mutations.ts`). Nova env var `NEXT_PUBLIC_API_URL` (`.env.local`, não commitada). `app/(app)/usuarios/page.tsx` (guard de master, redireciona pra `/` se não for), `components/users/UserTable.tsx` (menu de três pontos por linha), `NewUserModal.tsx` (convite + seleção de projetos via checkbox), `AccessModal.tsx` (gerenciar acesso por projeto + trocar avatar). `AdminBar.tsx` linkado de verdade.
54. **Bugs reais encontrados e corrigidos durante o teste no navegador** (usuário master real `diego@pmongerenciamento.com.br`, logado manualmente pelo usuário):
    - CORS: FastAPI não tinha `CORSMiddleware` — o preflight `OPTIONS` do navegador (`localhost:3000` → `localhost:8000`) voltava 405, `POST`/`PATCH` nunca chegavam a rodar. Corrigido em `main.py` (liberado só `http://localhost:3000` por enquanto, dev).
    - Menu de três pontos do `UserTable` ficava cortado/invisível — o `overflow-hidden` do container da tabela (usado pra arredondar cantos) cortava o dropdown absolutamente posicionado. Corrigido tirando o `overflow-hidden` e arredondando os cantos do `thead` diretamente.
    - `AccessModal` ficava com dados "congelados" da abertura do modal, não refletia mudanças depois de uma ação (ex.: conceder acesso não atualizava a lista na hora). Corrigido: `accessUser` deixou de ser `state` próprio e passou a ser derivado do prop `users` (`users.find(u => u.id === accessUserId)`), que já vem atualizado via `router.refresh()`.
55. **Validado ao vivo**: backend testado via curl de ponta a ponta com 2 usuários efêmeros + 1 projeto efêmero (todos criados/apagados com confirmação separada do usuário) — GET/POST/PATCH (block conta/projeto, unblock, reset senha, grant)/DELETE, incluindo o convite real batendo em `digfirst@gmail.com`. Frontend testado no navegador real (master de verdade): criar usuário bateu no rate limit de e-mail do Supabase (mesmo limite já visto antes, não é bug), mas o `POST` chegou certo no backend depois do fix de CORS; conceder/revogar/reativar acesso por projeto testado ao vivo com sucesso e sincronização correta. Upload de avatar não foi possível testar via automação de browser (limitação da ferramenta pra arquivo local), mas reusa o mesmo padrão já validado de `uploadProjectImage`.
    - Ficou um dado de teste real, inofensivo, no banco: `diego@` tem uma linha `active` em `project_members` pro projeto "00 PMON" (ele já é `owner_id` desse projeto de qualquer forma) — deixado de propósito, decisão do usuário.
56. Plano completo em `C:\Users\pmon_admin\.claude\plans\shiny-conjuring-otter.md`. Commits: `8e5c6d0` (implementação).
57. **Próximos passos**: módulo de importação no frontend (`POST /api/v1/upload` já pronto no backend, ainda sem UI), Pré-planejamento (item 41-48, ainda não implementado), e eventualmente `POST/GET/PATCH /api/v1/projects` no backend (gap registrado desde o item 40).

## Sessão 2026-07-03 (continuação) — Módulo Pré-planejamento (implementado)

58. **Módulo Pré-planejamento implementado** (itens 41-48, MVP "Opção B" aprovado): simulador de Linha de Balanço independente do MS Project, com 3 abas — Calendário, Serviços e lotes, Linha de balanço (só visualização, sem clique-para-editar no MVP). Plano completo aprovado via `EnterPlanMode` antes de codar, com 2 decisões de escopo confirmadas com o usuário nesta sessão:
    - **Defasagem entre pavimentos**: `sim_services` ganhou coluna `lag_days` (dias de defasagem entre pavimentos consecutivos do mesmo serviço, editável na aba "Serviços e lotes") — não estava no schema original que o usuário descreveu, adicionada após confirmação.
    - **Escopo do encadeamento**: cada grupo/torre (`sim_floors.group_name`) tem sequência independente de pavimentos — torres correm em paralelo, todas começando em `sim_studies.start_date`.
59. **Migration `007_pre_planejamento.sql`**: 6 tabelas novas — `sim_studies` (cenário: nome, data de início), `sim_services` (coluna da grade: nome, cor, `lag_days`), `sim_floors` (linha da grade: `group_name`/torre, `floor_name`, `order_index`), `sim_cycles` (célula da grade: serviço × pavimento, `duration_days`, unique constraint), `sim_links` (encadeamento auto-gerado, nunca editado à mão no MVP), `sim_holidays` (feriados nacionais pré-cadastrados + personalizados). RLS em todas, mesmo padrão de `tasks`/`dependencies` (dono via `projects.owner_id`, join até `sim_studies`) — não protege o caminho do backend (`DATABASE_URL` direto), mas mantém consistência.
    - **Encontrado durante a aplicação**: o usuário reportou "todas as tabelas criadas com sucesso", mas `sim_links` de fato não existia no banco (as outras 5 estavam lá) — só percebido quando o `PUT /ciclos` quebrou com `UndefinedTableError` na validação ao vivo. Resolvido rodando só o bloco de `sim_links` (tabela + índice + RLS + policy) que tinha ficado de fora.
60. **Backend**: `domain/pre_planejamento/holidays.py` — feriados nacionais brasileiros fixos + móveis (Carnaval/Sexta-feira Santa/Corpus Christi calculados a partir da Páscoa via algoritmo de Gauss/computus), gerados automaticamente na criação de um estudo (janela de 4 anos a partir do `start_date`). `domain/pre_planejamento/repository.py`: leitura direta via `asyncpg`; `replace_cycles` faz delete-and-reinsert transacional de `sim_services`/`sim_floors`/`sim_cycles`/`sim_links` (índices posicionais nos arrays de entrada, já que linhas novas da grade não têm UUID no momento do save) e auto-gera `sim_links` encadeando pavimentos consecutivos por `(serviço, grupo/torre)` usando o `lag_days` daquele serviço. `routes_pre_planejamento.py`: 6 endpoints (`GET/POST estudos`, `GET/PUT/DELETE estudo`, `PUT ciclos`) atrás de `get_current_user` + checagem explícita de que o projeto pertence ao dono (mesmo padrão de `process_import`, já que RLS não protege o backend).
    - **Decisão deliberada, fora do plano original**: não foi criado nenhum `scheduler.py` no backend — o plano listava essa função lá, mas nenhuma rota aprovada precisa de cronograma calculado (isso só é usado pra desenhar o gráfico, no cliente). Implementar isso em Python sem nada chamando seria código morto.
61. **Frontend**: `lib/project-modules.ts` ganhou o item "Pré-planejamento" entre "Importar cronograma" e "Linha de balanço" (ícone `IconCalendarStats`, já validado contra o `.d.ts` do pacote desde o item 26). `app/(app)/projetos/[projectId]/pre-planejamento/` — lista de cenários (`StudiesList.tsx` + `NewStudyModal.tsx`) e `[estudoId]/layout.tsx` (busca o estudo uma vez, repassa via `StudyContext.tsx`/`useStudy()` pras 3 abas, evitando 3 fetches duplicados). `lib/api/pre-planejamento.ts` (leitura server-side) / `pre-planejamento-mutations.ts` (escrita client-side) — reusa `lib/api/backend-client.ts` pela primeira vez fora do módulo de usuários, confirmando que virou o padrão certo de chamada ao backend.
    - `HolidayCalendar.tsx`: lista feriados (badge nacional/personalizado) + form de adicionar, salva a lista inteira via `PUT /estudos` (replace).
    - `CyclesGrid.tsx`: tabela estilo planilha (pavimento sticky à esquerda, serviços roláveis, agrupados visualmente por torre), célula = input de dias, cabeçalho de serviço com cor + nome + defasagem editáveis. Estado local até "Salvar" (não salva a cada tecla).
    - `lib/pre-planejamento/scheduler.ts`: porta TypeScript do algoritmo de cálculo de datas (só existe no frontend, ver item 60) — pra cada `(serviço, grupo/torre)` encadeia os pavimentos com ciclo daquele serviço, contando `duration_days` em dias úteis (pula fim de semana e feriados do estudo) e aplicando `lag_days` do serviço entre pavimentos consecutivos.
    - `components/charts/PreLoBChart.tsx`: **primeiro uso de verdade do D3** no projeto (dependência instalada desde o scaffold inicial, nunca usada) — `scaleBand`/`timeDay` do D3 pro cálculo de posição, renderização em HTML/React (não SVG imperativo). Cabeçalho de 3 níveis (mês/semana/letra do dia), fins de semana e feriados em cinza, linhas por pavimento com sub-linhas dinâmicas via "interval partitioning" (só expande quando há sobreposição de horário no mesmo pavimento), cores por serviço, sem clique-para-editar (MVP).
62. **Bugs reais encontrados e corrigidos durante o teste no navegador** (usuário master real, projeto real "00 PMON"):
    - `sim_links` faltando no banco (ver item 59).
    - `CyclesGrid.tsx` usava `window.prompt()` nativo pro botão "+ Pavimento" — travava a automação de browser (dialogs nativos bloqueiam o CDP) e destoava do resto da UI (todos os outros formulários usam modal próprio). Trocado por um modal comum (`Input` + `Button`, mesmo padrão de `NewStudyModal`).
    - `PreLoBChart.tsx`: rótulo do intervalo semanal calculava a semana como domingo-sábado (`day.getDate() - day.getDay()`), então mostrava uma data que não aparecia de fato nas colunas visíveis quando a primeira coluna renderizada era uma segunda-feira. Corrigido pra semana segunda-domingo (`(day.getDay() + 6) % 7`).
63. **Validado ao vivo**: backend testado via curl com 1 usuário + 1 projeto efêmeros (criados/apagados com confirmação separada) — GET/POST/PUT/DELETE de estudos, `PUT /ciclos` com 2 torres e 2 serviços com `lag_days` diferentes (4/4 vínculos gerados corretos, isolados por torre), isolamento por dono (404 em projeto de outro usuário) confirmado. Frontend testado no navegador com o cenário "Teste Browser" no projeto real "00 PMON": criação de cenário, calendário com os 44 feriados nacionais pré-populados (datas de Carnaval/Sexta-feira Santa/Corpus Christi conferidas manualmente contra a Páscoa real de 2026-2029, batendo certinho), grade de serviços × pavimentos com a mesma configuração validada no backend, Linha de Balanço renderizando com sub-linhas aparecendo exatamente nos pavimentos com sobreposição de serviços e ficando em linha única nos demais — matemática do encadeamento (datas de início considerando dias úteis + defasagem) conferida manualmente e batendo com o esperado. Cenário de teste excluído ao final, projeto real limpo.
64. Plano completo em `C:\Users\pmon_admin\.claude\plans\shiny-conjuring-otter.md`. Commit `895df05` (implementação).
65. **Próximos passos**: módulo de importação no frontend (`POST /api/v1/upload` já pronto no backend, ainda sem UI), e eventualmente `POST/GET/PATCH /api/v1/projects` no backend (gap registrado desde o item 40). Fora de escopo do MVP, registrado pra futuro: edição de ciclo/vínculo clicando na barra da Linha de Balanço (item 44 original), e mover o cálculo de cronograma pro backend se algum dia for preciso em outro lugar (relatório, exportação) além do gráfico.

## Sessão 2026-07-03 (continuação 2) — Estrutura WBS + refinamentos do Pré-planejamento

66. **Nova regra permanente de validação**: a partir desta sessão, **claude-in-chrome não é mais usado para validar mudanças de frontend** — só `tsc --noEmit` + `eslint`. A validação visual em navegador passou a ser feita manualmente pelo usuário.
67. **Mockups de referência criados** em `docs/mockups/` (calendário, ciclos, linha de balanço) — HTML estático aprovado pelo usuário, usado como base visual pros ajustes dos itens 68-69.
68. **"7 ajustes" pós-mockup implementados**: mini calendário mensal (`MiniCalendar.tsx`, novo), feriados nacionais/personalizados exibidos separadamente, coluna vertical de rótulo de grupo/torre na grade de ciclos, "ciclo padrão" com botão "Aplicar" pra preencher em massa, inputs de duração sem spinner nativo, adicionar múltiplos pavimentos de uma vez separados por `;`, pavimentos ordenados de baixo pra cima na Linha de Balanço (térreo embaixo, como no mockup).
69. **2 ajustes pós-revisão visual**:
    - Campo "Defasagem/Lag" removido da UI do cabeçalho de serviço (`CyclesGrid.tsx`) e do cálculo em `scheduler.ts` — decisão deliberada de escopo, defasagem entre tarefas volta como conceito quando a Estrutura WBS (item 70) tiver predecessoras de verdade, não faz sentido manter os dois modelos ao mesmo tempo.
    - **Cores de serviço passaram a ser atribuídas automaticamente**, não mais editáveis pelo usuário — fórmula de matiz por ângulo áureo pra garantir cores distintas mesmo com 50+ serviços: `hue = (index * 137.5) % 360`, saturação 65%, luminosidade 50% (`generateServiceColor()` em `CyclesGrid.tsx`). Uma paleta fixa de poucas cores foi proposta e rejeitada pelo usuário por não escalar.
70. **Estrutura WBS implementada** — funcionalidade mais importante pendente do módulo, modelo de predecessoras/sucessoras estilo MS Project:
    - **Correção de fundação necessária primeiro**: `repository.py::replace_cycles` fazia delete-and-reinsert cego de `sim_services`/`sim_floors`/`sim_cycles` a cada save da grade — como a WBS passaria a referenciar `sim_cycles.id`, isso destruiria os predecessores salvos a cada save trivial em "Serviços e lotes". Reescrito como upsert reconciliador (`_upsert_services`/`_upsert_floors`/`_upsert_cycles`): atualiza por `id` quando presente, insere quando ausente, apaga o que sumiu do payload — preserva UUID de tudo que continua existindo. `ServiceIn`/`FloorIn` ganharam `id` opcional; `CyclesGrid.tsx` passou a carregar e reenviar esse `id`.
    - **Migration `008_sim_wbs_overrides.sql`**: tabela dedicada pros predecessores editados manualmente (`cycle_id`/`predecessor_id`, unique constraint, RLS no mesmo padrão das demais `sim_*`) — decisão do usuário, não reaproveitar `sim_links` (que continua sendo só a sugestão de encadeamento automático).
    - **Backend**: `get_wbs_overrides`/`replace_wbs_overrides` no repository; novo endpoint `PUT /pre-planejamento/{project_id}/estudos/{estudo_id}/predecessores`; `GET estudo` passou a incluir `predecessors`.
    - **`scheduler.ts` reescrito**: de "encadeia por ordem de pavimento dentro do grupo" pra um forward-pass topológico de verdade (Kahn) sobre o grafo explícito de predecessores — tarefa sem predecessor começa em `study.startDate`, com predecessores começa no próximo dia útil após o maior fim entre eles. Ciclo no grafo (referência circular) não trava a tela, só cai no caso "sem predecessor válido". Nova função `suggestPredecessors()` reaproveita a lógica antiga (encadeamento por ordem) só como sugestão inicial editável do botão "Gerar estrutura automática".
    - **`WbsTable.tsx`** (aba nova, entre "Serviços e lotes" e "Linha de balanço"): árvore de 3 níveis, ID sequencial e código WBS recalculados por posição a cada render (mesmo comportamento do Task ID do MS Project, não armazenados). Predecessores digitados por ID (`5;3`), resolvidos internamente pro UUID do ciclo. Navegação por Tab/Enter/setas entre células.
    - **Outros itens do mesmo pacote**: exclusão de grupo/torre (botão no label vertical da grade, com `ConfirmDialog`), linhas da Linha de Balanço mais compactas (`ROW_HEIGHT` 32→22 em `PreLoBChart.tsx`).
    - Commit `9da9197`.
71. **Ajustes de UX na WBS** (rodada seguinte, mesma sessão):
    - **Hierarquia reorganizada** de Serviço→Torre→Pavimento pra **Torre→Serviço→Pavimento** (`buildRows()` em `WbsTable.tsx`) — bate com o jeito que o planejador pensa a estrutura (torre é a unidade de entrega).
    - **"Replicar torre"**: menu de ações (três pontinhos) na linha de torre — duplica pavimentos + ciclos com sufixo "(cópia)", remapeia só os predecessores internos à torre pros ciclos novos (os que apontam pra fora do grupo ficam de fora da cópia, de propósito). Executa na hora, sem esperar o "Salvar" geral — por isso `saveCycles`/`saveWbsOverrides` (`lib/api/pre-planejamento-mutations.ts`) passaram a devolver o `StudyDetail` atualizado (mapeamento snake_case→camelCase extraído pra `lib/api/pre-planejamento-mappers.ts`, reusado tanto na leitura server-side quanto na escrita client-side).
    - **Bug latente corrigido**: o estado local de duração/predecessores só era inicializado uma vez (no mount), então depois de qualquer `router.refresh()` (ex.: após "Replicar torre") os campos de ciclos novos apareciam vazios mesmo já salvos. Corrigido com `useEffect` resincronizando sempre que `study` muda.
    - **Drag fill + Ctrl+D** nos campos de Duração/Predecessores, estilo planilha — alcinha no canto da célula pra arrastar e preencher em sequência, `Ctrl+D` repete o valor da linha de cima.
    - Commit `06ee3ee`.
72. **2 bugs de ambiente encontrados e corrigidos durante o teste do usuário** (nenhum era erro de código — `tsc`/`eslint` continuaram limpos o tempo todo):
    - **CSS do Tailwind sumindo** (tela de login sem estilo): cache de build `.next` corrompido por ter 2 processos `next dev` escrevendo na mesma pasta ao mesmo tempo (um subiu sozinho na porta 3001 quando a 3000 já estava ocupada). Resolvido apagando `.next` e subindo um único processo limpo.
    - **404 ao criar cenário novo**: o processo do backend (`uvicorn`) não tinha sido reiniciado depois das mudanças de schema da WBS (item 70) — continuava servindo a resposta antiga sem o campo `predecessors`, o que quebrava `getStudy()` no frontend (`.map()` em `undefined`) e virava `notFound()`. Lição: **mudança de schema/rota no backend exige reiniciar o `uvicorn`** — hot-reload do Next não cobre o processo Python.
73. **Encerramento da sessão — resumo completo do dia** (módulo Pré-planejamento):
    1. Ajustes visuais alinhados aos mockups de `docs/mockups/` (item 68): mini calendário, feriados nacionais/personalizados separados, coluna de rótulo de grupo/torre, ciclo padrão + "Aplicar", inputs sem spinner, múltiplos pavimentos por `;`, pavimentos de baixo pra cima na Linha de Balanço.
    2. Cores de serviço automáticas via ângulo áureo: `hue = (index * 137.5) % 360`, saturação 65%, luminosidade 50% — distintas mesmo com 50+ serviços, não mais editáveis pelo usuário (`generateServiceColor()` em `CyclesGrid.tsx`).
    3. Campo "Defasagem/Lag" removido da grade de ciclos — encadeamento entre tarefas passou a ser controlado pelas predecessoras/sucessoras da Estrutura WBS, não fazia sentido manter os dois modelos.
    4. **Estrutura WBS implementada**: hierarquia Torre → Serviço → Pavimento, predecessoras digitadas por ID separadas por `;` (resolvidas internamente pro UUID do ciclo), sucessoras sempre calculadas (nunca editadas à mão), Início/Término calculados por `lib/pre-planejamento/scheduler.ts` (forward-pass topológico/Kahn sobre o grafo de predecessores).
    5. Botão "Replicar torre": duplica pavimentos + ciclos da torre inteira, remapeia só os predecessores internos à torre (os que apontam pra fora ficam de fora da cópia).
    6. Drag fill + Ctrl+D nos campos de Duração e Predecessores da WBS, estilo planilha.
    7. Migration `008_sim_wbs_overrides.sql` aplicada no Supabase (tabela dedicada de predecessores, separada de `sim_links`).
    8. Exclusão de grupo/torre implementada com `ConfirmDialog`.
    9. Linhas da Linha de Balanço mais compactas (`ROW_HEIGHT` 32→22 em `PreLoBChart.tsx`).
    10. CSS do Tailwind verificado e confirmado funcional (os 2 sumiços reportados eram cache `.next` corrompido e backend desatualizado, ver item 72 — não um problema de configuração do Tailwind em si).
    - Commits da sessão: `9da9197` (WBS inicial + ajustes visuais + cores + exclusão de grupo + LOB compacta), `06ee3ee` (hierarquia Torre→Serviço→Pavimento + replicar torre + drag fill/Ctrl+D).
74. **Pendências para a próxima sessão**:
    - Validação visual completa do módulo Pré-planejamento no navegador (esta sessão validou só via `tsc`/`eslint` + testes pontuais do usuário — falta uma passada de ponta a ponta pelas 4 abas).
    - Banner de período no calendário (ainda não especificado em detalhe — levantar o requisito com o usuário antes de planejar).
    - Teste do módulo com os sócios.
    - Itens mais antigos ainda em aberto: módulo de importação no frontend (`POST /api/v1/upload` já pronto no backend, ainda sem UI), `POST/GET/PATCH /api/v1/projects` no backend (gap desde o item 40).
    - Fora de escopo, registrado pra depois: tipos de dependência além de finish-to-start (SS/FF/FS+lag) na WBS, persistir estado de recolher/expandir da árvore.

## Sessão 2026-07-04 — Ajustes finais do Pré-planejamento e aprovação pro primeiro teste com sócios

75. **Migration `009_sim_studies_duration.sql`**: coluna `duration_months` (integer, nullable — não quebra cenários já existentes) em `sim_studies`. Aplicada direto no Supabase real via `asyncpg`/`DATABASE_URL` (porta 5432 alcançável desta vez, diferente da limitação de rede relatada no item 32; confirmação separada do usuário antes de rodar o `ALTER TABLE`).
76. **Campo "Prazo estimado (meses)" no modal "Novo cenário"** (`NewStudyModal.tsx`): terceiro campo obrigatório, número de meses. Fluxo completo: `CreateStudyRequest`/`StudyOut` (backend, `Field(gt=0)`), `Study`/`CreateStudyInput` (frontend), `pre-planejamento-mappers.ts`, `createStudy()`.
77. **Banner de período na aba Calendário** (`HolidayCalendar.tsx`, acima do mini-calendário/feriados): "Período do cenário: [início] → [término]" (término calculado a partir de `duration_months`, cenários antigos sem esse dado mostram "prazo não informado") + "Feriados gerados de [ano] a [ano]" (calculado a partir dos próprios feriados nacionais já persistidos, não de uma constante fixa no frontend).
78. **Botão "Replicar torre" adicionado na aba "Serviços e lotes"** (`CyclesGrid.tsx`): antes só existia na aba "Estrutura WBS" (item 71), escondido atrás de um menu "⋯" e só visível pra torres que já tinham ao menos um ciclo preenchido — por isso o usuário reportou que "sumiu". Agora também aparece como ícone de cópia no label vertical de cada grupo/torre em "Serviços e lotes", duplicando pavimentos + durações localmente (mesmo padrão de "+ Grupo"/"+ Pavimento" — só grava no banco ao clicar "Salvar", diferente da versão da Estrutura WBS que salva na hora).
79. **Edição inline do nome do grupo/torre** (`CyclesGrid.tsx`, label vertical): clique no nome vira `<input>`, Enter ou clicar fora (blur) salva (renomeia o grupo e todos os pavimentos vinculados), Esc cancela. Nome vazio ou colidindo com outro grupo já existente é recusado (evita fundir dois grupos sem querer). Não existia nenhum componente de "clique-para-editar" no projeto até agora (pesquisado antes de implementar) — padrão novo, sem reaproveitar código existente.
80. **Bug de ambiente recorrente**: cache `.next` corrompido de novo (mesma causa do item 72 — processo `next dev` zumbi ocupando a porta 3000 de uma sessão anterior). Resolvido matando o processo (`Stop-Process`) e apagando `.next` antes de subir um servidor novo limpo.
81. **Módulo Pré-planejamento aprovado para o primeiro teste com os sócios**, com os ajustes 75-79 acima concluídos e validados via `tsc --noEmit` + `eslint` (sem `claude-in-chrome`, regra do item 66).
82. Commits: `8c242e2` (prazo estimado + banner de período + replicar torre em "Serviços e lotes" + migration 009), `640c371` (edição inline do nome do grupo/torre).
83. **Pendências para a próxima sessão**:
    - Validação visual completa de ponta a ponta ainda não feita nesta sessão (regra do item 66 — só `tsc`/`eslint`); depende do teste real com os sócios.
    - Feedback do primeiro teste com os sócios (a ser incorporado assim que acontecer).
    - Itens mais antigos ainda em aberto: módulo de importação no frontend (`POST /api/v1/upload` já pronto no backend, ainda sem UI), `POST/GET/PATCH /api/v1/projects` no backend (gap desde o item 40).
    - Fora de escopo, registrado pra depois: tipos de dependência além de finish-to-start (SS/FF/FS+lag) na WBS, persistir estado de recolher/expandir da árvore.

## Sessão 2026-07-05 — Deploy do frontend no Vercel

84. **Primeiro deploy do frontend em produção**: `vercel.json` na raiz (buildCommand/outputDirectory apontando pra `frontend/`) foi tentado primeiro, depois removido em favor de configurar **Root Directory = `frontend`** direto nas configurações do projeto no Vercel (decisão do usuário — mais simples que manter `vercel.json` sincronizado).
85. **Saga de troubleshooting do `MIDDLEWARE_INVOCATION_FAILED`** (`middleware.ts`, autenticação via `@supabase/ssr`):
    - Hipótese inicial (não confirmada por log real): `createServerClient` do `@supabase/ssr` toca `process.version` (API só de Node.js), incompatível com o Edge Runtime padrão do middleware — tentativa de corrigir com `runtime: "nodejs"` na `config` exportada (suportado de forma estável desde o Next.js 15.5, sem flag experimental).
    - **Piorou**: `runtime: "nodejs"` expôs um erro novo e confirmado por log real (`SyntaxError: Cannot use import statement outside a module`), causado por uma dependência transitiva ESM-only do `@supabase/supabase-js` sendo carregada via `require()` pelo empacotador de função serverless do Next — revertido de volta pro Edge Runtime padrão (sem `runtime` na config).
    - Log real seguinte mostrou `ReferenceError: __dirname is not defined`, com caminho `/var/task/frontend/middleware.js` (`/var/task/` é especificamente onde a Vercel roda funções **Node.js**, nunca Edge) — bundle local do middleware auditado e reauditado (4 rebuilds limpos consecutivos) sem nenhum `__dirname` ou `@supabase` em `server/middleware.js`/`server/edge-runtime-webpack.js`, mesmo depois de o usuário confirmar que o commit no ar era o certo. Padrão de logs não batendo com o build local se repetiu por 3-4 rodadas seguidas.
    - **Correção adotada, independente do mistério do log**: `middleware.ts` reescrito pra não importar mais `@supabase/ssr` — vira uma checagem simples de **presença** do cookie `sb-ttqtefwntkgpgatrcyps-auth-token` (com `startsWith`, porque `@supabase/ssr` fatia esse cookie em `.0`/`.1`/... quando o valor é grande), sem validar assinatura/expiração do JWT. Trade-off aceito pelo usuário: a validação de verdade continua no client (Supabase Auth) e no backend (`verify_token`); o middleware nunca foi a camada de segurança real, só o guard de redirecionamento `/login` ↔ resto do app.
    - Matcher do middleware ampliado pra excluir também `favicon.png`, `logo` e `public/` (antes só excluía `favicon.ico`) — mudança de baixo risco, mas **não** era a causa do `__dirname` (mesma função roda igual em qualquer rota casada).
86. **Causa raiz real, achada só depois de todo o troubleshooting de código acima**: nada disso era o problema. O time **"PMON" no Vercel era um time Hobby**, que bloqueia/exige verificação quando o autor do commit não é reconhecido como colaborador — isso gerava os erros de deploy (inclusive, possivelmente, alguns dos `MIDDLEWARE_INVOCATION_FAILED` — não dá mais pra ter certeza de quanto era isso vs. os bugs reais de código corrigidos no item 85, já que as duas coisas aconteciam em paralelo). **Resolvido excluindo o projeto do time PMON e recriando na conta pessoal do Vercel do usuário (`pmongerenciamento`)** — contas pessoais Hobby não verificam autor de commit em repositórios públicos.
87. **Frontend deployado com sucesso em produção no Vercel** — tela de login PMON funcionando ao vivo.
    - URL Vercel: https://gestao-obras-five.vercel.app
    - Login: https://gestao-obras-five.vercel.app/login
88. Commits da saga do middleware: `5e5a2a5` (tentativa `runtime: "nodejs"`, revertida), `e3c3318` (revert pro Edge Runtime), `187df92` (commit vazio-ish só pra forçar rebuild), `b2539d2` (middleware minimalista sem `@supabase/ssr`, versão que de fato funcionou em produção), `b349cea` (ajuste de matcher — favicon.png/logo/public).
89. **Senha do usuário `diego@pmongerenciamento.com.br` redefinida** via Admin API (script Python ad-hoc, rodado pelo `.venv` do backend e apagado logo depois — não fica no repo por conter a senha em texto puro). Confirmado via `update_user_by_id`.
90. **Login testado direto na API do Supabase** (`sign_in_with_password`, script ad-hoc, mesmo padrão de descarte) — credencial funcionando, sessão/`access_token` retornados com sucesso. Isso isolou o problema: a credencial estava certa, o bug era em outro lugar.
91. **Login funcionando via API mas falhando no frontend em produção**: `LoginForm.tsx` engolia qualquer erro de `signInWithPassword` na mesma mensagem genérica "E-mail ou senha inválidos." — adicionado `console.error(signInError)` temporário (marcado com `// TODO: remover`) pra expor o erro real no DevTools em vez de adivinhar. Commit `6bf53a2`.
92. **Causa raiz encontrada**: `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` cadastrada no Vercel contém um caractere inválido (fora de ISO-8859-1) — o navegador rejeita ao montar o header HTTP `apikey`, erro `String contains non ISO-8859-1 code point`. Suspeita: caractere invisível/smart-quote introduzido ao colar a chave no painel da Vercel.
93. **Próximos passos**: atualizar `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` no Vercel (colar de novo com cuidado pra não reintroduzir o caractere inválido) e redeployar; remover o `console.error` temporário de `LoginForm.tsx` (item 91) depois de confirmar o login funcionando; deploy do backend no Railway; cadastrar usuários dos sócios; testar o fluxo completo online (frontend Vercel + backend Railway + Supabase). Itens mais antigos ainda em aberto: módulo de importação no frontend, `POST/GET/PATCH /api/v1/projects` no backend (gap desde o item 40).
94. **Env var corrigida e `console.error` removido** (commits `06b3e0e` guard, `73de92e` remoção) — login em produção confirmado funcionando depois da correção do caractere inválido na chave.
95. **Guard adicionado em `lib/api/users.ts::listUsers()`** (commit `06b3e0e`): erro real em produção era `Failed to parse URL from undefined/api/v1/users` — `NEXT_PUBLIC_API_URL` (nome certo da variável; `NEXT_PUBLIC_BACKEND_URL` não existe no código) undefined no build, porque o backend ainda não estava deployado. Guard retorna `[]` em vez de lançar exceção quando a variável não está setada — só na leitura (`listUsers`), não nas mutações (criar/bloquear usuário), que devem continuar mostrando erro de verdade se o backend estiver fora do ar.
96. **Saga de configuração de deploy do backend no Railway** — várias iterações de arquivo de config até chegar num formato funcional:
    - `backend/railway.json` (`NIXPACKS` builder) + `backend/Procfile` + `backend/nixpacks.toml` (`jdk17`, pro `mpxj`/`JPype1`) — primeira tentativa.
    - Trocado pra `backend/railway.json` com builder `RAILPACK` — mas o `nixpacks.toml` é specific do Nixpacks, então o JDK provavelmente pararia de ser instalado (não confirmado se chegou a dar erro, trocado antes de testar).
    - Trocado de novo: `railway.json` (em `backend/`) removido, criado **`railway.toml` na raiz do repo** (não em `backend/`) com `buildCommand`/`startCommand` fazendo `cd backend &&` — decisão de manter só um arquivo de config pra evitar a mesma ambiguidade de Root Directory que já tinha acontecido no Vercel com `vercel.json`.
    - Ajustes seguintes no `railway.toml`: `pip3`/`python3 -m uvicorn` explícitos, depois removido `buildCommand` (deixar o Railpack auto-detectar Python) — mas auto-detecção depende de achar `requirements.txt` na raiz que o Railway escaneia, que só existe em `backend/`, então só funciona se o Root Directory do serviço no Railway estiver setado como `backend`.
    - **Builder final: `dockerfile`** (`builder = "dockerfile"`, `dockerfilePath = "backend/Dockerfile"`) — `backend/Dockerfile` criado com `python:3.11-slim` + `default-jdk-headless` (Java 17 no Debian Bookworm) + `JAVA_HOME=/usr/lib/jvm/default-java` (JPype autodetecta via essa env var, confirmado lendo `app/infra/mpxj/jvm.py`). `COPY` corrigido pra `COPY backend/requirements.txt .`/`COPY backend/ .` assumindo que o contexto de build é a raiz do repo (onde o `railway.toml` fica) — não confirmado 100% pela documentação da Railway, mas é a convenção padrão de Docker/CI quando só se especifica `dockerfilePath` sem um `context` separado.
    - `healthcheckTimeout = 300` adicionado (tempo de subir a JVM do MPXJ).
    - `CMD` do Dockerfile ganhou um debug temporário (`python -c "print(...)"` das env vars `SUPABASE_URL`/`DATABASE_URL` antes do `uvicorn`) pra diagnosticar startup — ainda não removido.
97. **Causa raiz real do erro de conexão com o Supabase no Railway**: porta 5432 (conexão direta) bloqueada pela rede do Railway — precisa do **connection pooler**. Testado empiricamente (conexões reais, não suposição) contra 16 regiões do formato documentado pela Supabase (`aws-0-<região>.pooler.supabase.com:6543`, user `postgres.<ref>`) — **nenhuma funcionou** (erro `tenant/user not found` em todas). O formato que **de fato funciona pra este projeto**: mesmo host da conexão direta, só trocando a porta — `postgresql://postgres:<senha>@db.ttqtefwntkgpgatrcyps.supabase.co:6543/postgres` — **sem** `?pgbouncer=true` (esse parâmetro quebra a conexão do asyncpg aqui, erro `unsupported startup parameter: pgbouncer`). `DATABASE_URL` no Railway precisa ser atualizada pra esse formato.
98. **Correção do item 97**: mesmo com a `DATABASE_URL` na porta 6543 (formato confirmado funcionando a partir do ambiente do Claude Code), a conexão a partir do **Railway** continuou falhando. Testado também SSL explícito no `asyncpg.create_pool()` (`pool.py`, commit `4be8f9e`) — sem sucesso. **Causa raiz real**: o plano **Free do Railway bloqueia conexões TCP outbound** nas portas 5432 e 6543 — não é questão de porta, formato de URL ou SSL, é bloqueio de rede do próprio plano.
99. **Análise de impacto apresentada (não implementada) pra migrar o backend de asyncpg/pool direto pra só `supabase-py` (REST via HTTPS/443)** — decisão de adiar pra uma segunda rodada, não implementar agora. Achados principais da análise:
    - **`auth.users` é inacessível via PostgREST** (Supabase não expõe o schema `auth`) — `list_users`/`get_user` (`domain/users/users.py`) precisariam voltar pra Admin API paginada, perdendo o motivo original de ter usado SQL direto.
    - **`COPY` (bulk insert de tasks/dependencies/task_progress, `infra/db/bulk.py`) não tem equivalente em REST** — a alternativa (INSERT em lote via JSON) é bem mais lenta/arriscada pra cronogramas de 10-20 mil linhas (ver `docs/referencia-projeto.md`).
    - **Atomicidade transacional se perde** sem reescrever a lógica de negócio em funções Postgres (RPC/plpgsql) — afeta principalmente `process_import` (upload de cronograma) e o upsert reconciliador de `replace_cycles`/`replace_wbs_overrides` (Pré-planejamento).
    - Mecanicamente, remover o pool do `app/main.py` é trivial, mas cascateia pra reescrever `core/dependencies.py::get_db` e todas as 11 rotas + funções de domínio que hoje recebem `conn: asyncpg.connection.Connection`.
100. **Decisão da sessão**: liberar o primeiro teste com os sócios **sem** o backend no ar, em vez de bloquear o teste esperando a decisão de arquitetura do item 99.
101. **Frontend em produção, testado e funcionando**:
     - URL: https://gestao-obras-five.vercel.app
     - Login confirmado funcionando com `diego@pmongerenciamento.com.br`.
     - **3 sócios cadastrados manualmente no Supabase** (fora do fluxo normal de convite pelo sistema, que depende do backend) para participar do primeiro teste.
102. **Funcionalidades disponíveis no teste** (não dependem do backend — são frontend-direto-Supabase): login, cadastro de projetos, módulo Pré-planejamento completo (cenários, calendário, serviços/lotes, Estrutura WBS, Linha de Balanço).
103. **Funcionalidades indisponíveis sem o backend no ar**: gestão de usuários pelo sistema (tela `/usuarios` mostra lista vazia por causa do guard do item 95, mas convite/bloqueio/exclusão não funcionam), upload de cronograma `.mpp` (`POST /api/v1/upload`, depende do MPXJ/JVM que só roda no backend).
104. **Estratégia de backend a decidir na próxima rodada** (nenhuma decisão tomada ainda): (a) upgrade pro plano Railway Hobby (US$5/mês, provavelmente libera TCP outbound — mais barato e rápido que a alternativa) vs. (b) reescrever as operações de banco usando `supabase-py`/REST (ver perdas reais no item 99 — trabalho maior, some com `COPY` e atomicidade transacional sem RPCs).
105. **Próximos passos**: coletar feedback dos sócios do primeiro teste; decidir a estratégia do backend (item 104); implementar página de reset de senha de verdade (hoje "Esqueceu a senha?" em `LoginForm.tsx` é só texto desabilitado, sem fluxo). Itens mais antigos ainda em aberto: módulo de importação no frontend, `POST/GET/PATCH /api/v1/projects` no backend (gap desde o item 40).

## Sessão 2026-07-06 — Pré-planejamento 100% migrado pra Supabase direto

106. **Módulo Pré-planejamento 100% migrado de "frontend → backend Railway → Supabase" pra "frontend → Supabase direto"** — Railway deixa de ser necessário pra esse módulo especificamente (continua necessário pra upload de `.mpp` e gestão de usuários, ver item 104/108). Migração feita em 3 commits, todos os 6 endpoints antigos de `routes_pre_planejamento.py` substituídos por leitura/escrita direto no Supabase a partir do frontend:
    - `2faf557`: `createStudy`/`updateStudy`/`deleteStudy`.
    - `861900c`: `getStudy`/`listStudies` — corrigiu 404 em produção (o backend Railway não estava respondendo, ver item 103).
    - `c0d8b21`: `saveCycles`/`saveWbsOverrides`, os dois mais complexos (grade de serviços×pavimentos e predecessores da Estrutura WBS).
107. **`saveCycles`/`saveWbsOverrides` migrados como upsert direto no Supabase** — reimplementa no frontend (TypeScript, `@supabase/supabase-js`) a mesma lógica de upsert reconciliador que existia em Python no backend (`repository.py::_upsert_services`/`_upsert_floors`/`_upsert_cycles`, item 70): atualiza por `id` quando presente, insere quando ausente, apaga o que sumiu do payload — preserva UUID de tudo que continua existindo, essencial pra não quebrar os predecessores da WBS a cada save da grade.
108. **PENDÊNCIAS PARA PRÓXIMA RODADA**:
     a. **Reavaliar estrutura do banco**: revisar schema, RLS, índices, e se o modelo atual comporta o crescimento do sistema — ainda mais relevante agora que parte da escrita é frontend-direto-Supabase (RLS passa a ser a única linha de defesa real nesses caminhos, não só um padrão de consistência como era quando tudo passava pelo backend com `DATABASE_URL` direto).
     b. **Mapear custos mensais**: Vercel (hoje gratuito), Railway (necessário pra upload `.mpp` e gestão de usuários — ver item 104, plano Free bloqueia TCP outbound), Supabase (hoje gratuito), outros serviços eventualmente envolvidos.
     c. **Backend Railway ainda necessário** pra upload de `.mpp` (MPXJ/JVM só roda lá) e gestão de usuários (Admin API do Supabase Auth) — decidir estratégia: (i) upgrade pro plano Hobby (US$5/mês, provavelmente libera TCP outbound) vs. (ii) reescrever essas operações com `supabase-py`/REST (perdas já mapeadas no item 99: `auth.users` inacessível via PostgREST, `COPY` sem equivalente REST, atomicidade transacional se perde sem RPCs).
109. **Sistema atual funcionando em produção para o primeiro teste com os sócios**: login, cadastro de projetos e módulo Pré-planejamento completo (cenários, calendário, serviços/lotes, Estrutura WBS, Linha de Balanço) — tudo frontend-direto-Supabase, sem depender do backend Railway estar no ar.
110. **MIGRATION 010 — melhorias de schema, pendente pra depois do primeiro teste com os sócios (NÃO aplicar durante o teste)**, levantada na revisão de schema desta sessão (achados registrados no item 108a):
     - `DROP TABLE sim_links` (órfã — confirmado por grep que nenhum código de frontend ou backend lê/escreve nela desde a migração de `saveCycles`/`saveWbsOverrides` pra Supabase direto, item 107).
     - Índice em `projects.owner_id` (hoje sem nenhum índice além da PK, apesar de ser o filtro de toda policy RLS do banco e de `listProjects()`).
     - Índice composto em `task_progress (snapshot_id, task_id)` (hoje só índices simples separados por coluna).
     - Índice composto em `snapshots (project_id, is_baseline)` e `(project_id, reference_month)` (hoje só `idx_snapshots_project_id`).
     - Revisão aprofundada das policies RLS (todas as 7 tabelas escritas direto pelo frontend — `projects`, `sim_studies`, `sim_services`, `sim_floors`, `sim_cycles`, `sim_holidays`, `sim_wbs_overrides` — usam `for all`, cobrindo SELECT/INSERT/UPDATE/DELETE com a mesma regra; RLS virou a linha de defesa real nesses caminhos, não só padrão de consistência, ver item 108a).
     - Limpeza de `pending_imports` expirados (tabela tem `expires_at` mas nenhum job/cron remove linhas vencidas).

## Sessão 2026-07-07 — Migrations 011-015 (Clientes/CRM), ambiente de staging, bug de middleware corrigido

111. **Migrations `011` a `015` criadas em `backend/migrations/`** (branch `feature/clientes-crm`, ainda não mergeada em `main`), todas aditivas com rollback documentado no cabeçalho de cada arquivo:
     - `011_create_clients.sql`: tabela `clients` (code único, legal_name, cnpj nullable, dados de contato).
     - `012_create_service_types.sql`: tabela `service_types` + 5 seeds (`SVC-001` a `SVC-005`, sendo `SVC-005` "Outros" com `requires_manual_description = true`).
     - `013_alter_projects_add_client.sql`: `projects.client_id`/`project_code` + índice único composto `(client_id, project_code)` parcial (só quando ambos não nulos — projetos antigos sem cliente continuam sem restrição).
     - `014_create_billing_entities.sql`: tabela `billing_entities` (SPE), `project_id` único (1 SPE por projeto).
     - `015_create_teams.sql`: tabelas `teams`/`team_members` (`partner_tier` com CHECK `founding`/`associate`, unique `(team_id, profile_id)`), `projects.team_id`, `profiles.system_role` (texto livre, sem CHECK).
112. **Validação em 2 rodadas**:
     - Primeiro em transação com `ROLLBACK` contra o Supabase de **produção** (13/13 sub-testes passaram — constraints de unicidade, CHECK e nullable comportando exatamente como esperado; confirmado por leitura pós-rollback que o schema real voltou ao estado anterior, nada persistido).
     - Depois aplicadas de verdade (`COMMIT`) no projeto de **staging** (ver item 113) e re-testadas sem rollback: 14/14 sub-testes passaram (mesmo conjunto de testes + seed de dados reais criados em staging pra exercitar as FKs).
113. **Projeto Supabase de staging criado** (ref `gesqstdtbbdhlravddhd`), separado de produção:
     - `frontend/.env.staging` e `backend/.env.staging` criados (gitignorados via `.env.*` do `.gitignore` raiz) — senha do banco de staging URL-encoded (`urllib.parse.quote`) por conter caracteres especiais.
     - Schema completo (`001` a `015`) aplicado do zero em staging, incluindo bootstrap de dado de teste (3 usuários no Auth + projetos/clients/team_members) necessário pra exercitar as FKs de `profiles`/`projects.owner_id`.
     - `dotenv-cli` instalado como devDependency + script `"dev:staging": "dotenv -e .env.staging -- next dev"` no `frontend/package.json` — Next.js não carrega `.env.staging` automaticamente, e o log `Environments: .env.local` no boot é só informativo (lista arquivos `.env*` encontrados), não indica qual valor vence; confirmado por teste direto que os valores de staging realmente sobrepõem os de `.env.local`.
     - Backend local (`uvicorn`) apontado pro Postgres de staging via variáveis de ambiente exportadas no shell antes de subir o processo (`DATABASE_URL`/`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` de `backend/.env.staging`) — `backend/.env` de produção nunca foi tocado.
     - Usuário `diego@pmongerenciamento.com.br` já existia no Auth de staging (criado manualmente antes desta sessão); senha temporária redefinida via Admin API só pra teste.
114. **BUG DE PRODUÇÃO ENCONTRADO E CORRIGIDO — `middleware.ts`**: o nome do cookie de sessão estava hardcoded com o ref do projeto Supabase de produção (`sb-ttqtefwntkgpgatrcyps-auth-token`, `startsWith`), em vez de um padrão genérico. Nunca deu problema em produção porque só existia um projeto/ref; ao testar contra staging (ref diferente), o login ficava preso em "Entrando..." — a sessão era criada com sucesso no Supabase Auth (confirmado via chamada direta ao endpoint `/auth/v1/token`, 200 com token válido), mas o middleware nunca reconhecia o cookie e revertia o redirect de volta pra `/login` silenciosamente (sem erro de JS).
     - Corrigido pra regex `/^sb-.*-auth-token/`, compatível com qualquer ref de projeto. Validado (sem abrir navegador — só requisições HTTP diretas simulando os nomes de cookie): sem cookie → redireciona pra `/login` (307); cookie de staging (inteiro e fatiado `.0`) → passa (200); cookie de produção → continua passando (200, sem regressão).
     - Commit `b151e40` na branch `feature/clientes-crm` (junto com `dotenv-cli`/script `dev:staging` do item 113).
115. **Decisões de arquitetura (CRM/Clientes, Fase 1 — resumo; detalhe completo no planejamento anterior)**:
     - Cliente = grupo/portfólio (N projetos, N SPEs).
     - SPE vinculada ao projeto, não ao cliente (`billing_entities.project_id` único).
     - Funil de vendas simplificado: prospect → proposta → negociação → fechamento, sem tabela de "oportunidade" separada — reaproveita `clients`/`projects` em estágio de rascunho.
     - Rateio de despesas fica no lançamento/recorrência (não em regra fixa por cliente/projeto).
     - Time = centro de custo: Diego/Murillo `founding`, Carlos/Weslley `associate`.
116. **Pendências para a próxima sessão**:
     - Tela de Clientes (UI) ainda não implementada — só schema e mockup visual validados.
     - Teste de regressão completo em staging (cadastro de projeto + Linha de Balanço) ainda não refeito depois do fix do middleware — só o login foi reconfirmado (item 114).
     - PR de `feature/clientes-crm` → `main` ainda não aberto.
     - Tabelas de Propostas, SPE (schema de `billing_entities` já existe, sem UI), Reembolsos, CRM em geral — ainda sem código, só desenho/planejamento.
     - Itens mais antigos ainda em aberto: módulo de importação no frontend, `POST/GET/PATCH /api/v1/projects` no backend (gap desde o item 40), estratégia de backend Railway (item 104/108c).
117. **Não fazer ainda** (registrado explicitamente pelo usuário):
     - Não aplicar migrations `011-015` em produção.
     - Não mergear `feature/clientes-crm` em `main`.
     - Não trocar a senha do banco de produção agora (adiado por decisão do Diego até o sistema estar mais maduro).
     - Não remover o comentário residual em `middleware.ts` que ainda menciona `startsWith` (cosmético, não afeta funcionamento — texto do comentário não foi atualizado quando a implementação virou regex).

## Sessão 2026-07-08 — Sistema de permissões por módulo (019-023), tela de Clientes, funil de propostas, análise de concorrente

118. **Migrations `016` a `023` criadas em `backend/migrations/`** (branch `feature/clientes-crm`, ainda não mergeada), cada uma testada em transação com `ROLLBACK` contra staging (`gesqstdtbbdhlravddhd`) antes de ser aplicada de verdade (`COMMIT`):
     - `016`/`017`: habilita RLS em `clients` e nas 4 tabelas restantes (`service_types`, `teams`, `team_members`, `billing_entities`) com fallback `to authenticated` (gap encontrado: essas tabelas não tinham RLS nenhuma desde as migrations 011-015).
     - `018`: tabela `contracts` (contratos por projeto), mesmo fallback `to authenticated` com TODO.
     - `019`: `profile_modules` + `has_module_access()` — primeiro controle de acesso por módulo (`crm`/`financeiro`/`engenharia`/`reembolso`), FK `profile_id` com `on delete cascade` (acesso não é histórico, não faz sentido reter linha órfã quando a conta é removida). Função `security definer` pra evitar recursão de RLS na própria leitura de `profile_modules`.
     - `020`: simplifica `billing_entities` — remove `bank_name`/`bank_agency`/`bank_account` (não fazem sentido no fluxo real: o boleto é emitido *contra* a SPE, não pago *pra* ela; nenhuma linha real tinha esses campos preenchidos, confirmado antes do `DROP COLUMN`).
     - `021`: troca o fallback `to authenticated` por `has_module_access()` real em `clients`/`billing_entities`/`contracts` — nomes reais das policies existentes confirmados via `pg_policies` antes de escrever os `DROP POLICY` (divergiam do esperado: `clients` e `billing_entities` tinham 2 policies separadas, select+write, não uma única `_all_authenticated` como se assumia).
     - `022`: `proposals` + `proposal_cost_assumptions` + `projects.pipeline_stage` (funil de vendas: `prospect` → `proposta` → `negociacao` → `fechado_ganho`/`fechado_perdido`) — `proposals` espelha as mesmas condições comerciais de `contracts` (`payment_type`, `value`, `installments_count`, `signed_date`, `first_due_date`), copiadas pra `contracts` no momento do fechamento, não recalculadas. `proposal_cost_assumptions` com FK `on delete cascade` pra `proposals`.
     - `023` — **refatoração**: catálogo de permissões configurável (`modules` + `resources` + `permissions` + `has_permission()`), substituindo `has_module_access()` hardcoded nas 8 tabelas governadas (`clients`, `billing_entities`, `contracts`, `proposals`, `proposal_cost_assumptions`, `service_types`, `teams`, `team_members`). Sem "leitura pública" implícita — módulo sem permissão cadastrada não acessa nada (nem lê). `has_module_access()` (019) mantida, ainda usada só por `profile_modules_write_financeiro` (fora do escopo desta refatoração).
119. **Seed real em staging**: Diego com os 4 módulos em `profile_modules`. Backfill do profile do Diego que faltava em `profiles` — a conta em `auth.users` foi criada antes da migration `005` (trigger `trg_on_auth_user_created`) existir, então o trigger nunca retroagiu pra ela; encontrado ao consultar `profiles`/`auth.users` lado a lado antes do seed, corrigido com `insert ... on conflict do nothing` antes do seed dos módulos.
120. **Matriz de permissões final** (persistida na tabela `permissions`, 14 linhas): CRM lê/escreve `clients`/`billing_entities`/`contracts`/`proposals`/`proposal_cost_assumptions`/`service_types` (não escreve `teams`/`team_members`); Financeiro lê tudo, escreve só `billing_entities`/`service_types`/`teams`/`team_members`; Engenharia e Reembolso sem nenhuma permissão cadastrada ainda nessas 8 tabelas (módulos existem em `profile_modules` mas não têm linha em `permissions` — bloqueio total, não é omissão).
121. **Tela de Clientes (frontend) completa**: listagem + formulário inline (`frontend/app/(app)/clientes/`, `frontend/components/clients/`, `frontend/lib/api/clients.ts`/`client-mutations.ts`, `frontend/types/client.ts`), testada em staging.
122. **Decisões de arquitetura**:
     - Acesso por módulo fica configurável em tabela (`permissions`), não hardcoded em policy — Diego (admin master) vai poder ajustar via painel futuro, sem depender de migration nova pra cada mudança de regra.
     - Acesso por linha (ex.: quais projetos um engenheiro específico vê) continua responsabilidade de `project_members` (já existente) — o catálogo novo é só grant grosso por tabela inteira, não substitui o controle fino existente.
     - Soft-delete (`deactivated_at` em `profiles`) definido como direção pra Gestão de Usuários — não implementado ainda, só registrado como decisão.
     - SPE (`billing_entities`) sem dados bancários (ver item 118/020). CRM cadastra por padrão, mas Financeiro também pode reatribuir o faturamento pra uma SPE criada depois (caso pontual observado na prática — por isso Financeiro tem `write=true` em `billing_entities` na matriz, não só `read`).
123. **Bugs encontrados e corrigidos durante o processo de teste (fora do schema)**:
     - Scripts de teste que simulam sessão de usuário (`SET LOCAL ROLE authenticated` + `request.jwt.claims`) vazando pra fora da savepoint quando a troca de identidade acontecia *antes* de entrar na função isolada, não *dentro* dela — `ROLLBACK TO SAVEPOINT` só desfaz um `SET LOCAL` se ele tiver acontecido depois que a savepoint foi criada. Corrigido em 2 pontos de `test_migration_023.py` (o teste direto de `has_permission()` no passo 3, e o loop de 8 recursos × 4 identidades no passo 4). Lição registrada: toda simulação de sessão de usuário em teste precisa ficar contida dentro da própria função/savepoint, nunca ser setada solta antes dela.
     - `python3` resolvido pelo Git Bash neste ambiente pode cair no Python nativo do Windows (`WindowsApps/python3`), que não traduz caminho POSIX `/tmp/...` — usar o caminho Windows real (via `cygpath -w`) evita um falso positivo de "arquivo corrompido"/`FileNotFoundError` que não tinha nada a ver com o conteúdo do script.
124. **Análise de concorrente registrada como referência de UX** (imagens de alta resolução trazidas pelo usuário): dashboard com 3 cenários (Atual/Linha de Base/Desafio), Escadinha, Gantt, Linha de Balanço, Planejamento Semanal com PPC, Suprimentos com funil de 5 etapas, Vincular Orçamento de Receita — guardado pra quando chegarmos nos módulos de Engenharia/Financeiro; nenhuma ação tomada ainda.
125. **Pendências para a próxima sessão**:
     - Seed de `profile_modules` pros outros 5 (Murillo/Carlos/Weslley/Camila/Thiago) — só existem em produção, não em staging; fica pra quando essas migrations forem aplicadas em produção de verdade.
     - Telas do funil de vendas (prospect → proposta → negociação → fechamento) — schema pronto (item 118/022), UI não iniciada.
     - Painel de administração de permissões (Diego como master editando a tabela `permissions` via UI) — schema pronto (item 118/023), UI não iniciada.
     - PR de `feature/clientes-crm` → `main` ainda não aberto.
126. **Não fazer ainda** (registrado explicitamente pelo usuário):
     - Não aplicar migrations `016-023` em produção.
     - Não mergear `feature/clientes-crm` em `main`.
     - Não trocar a senha do banco de produção (decisão adiada por Diego, mesma pendência do item 117).

## Sessão 2026-07-09 — Módulo CRM completo (dashboard, pipeline, fechamento de negócio)

127. **IMPLEMENTADO** — migrations 024-029 criadas, testadas (transação com rollback) e aplicadas em staging, mais o frontend do módulo CRM inteiro:
     - **Migration 024**: leitura de `projects` liberada pro módulo CRM (visão cross-owner pro funil/ranking — sem isso, cada usuário só via os próprios projetos).
     - **Migration 025**: `profile_display_name()` — nome de exibição com fallback pro e-mail, via RPC `security definer`.
     - **Migration 026**: `project_stage_history` — histórico automático de tempo em cada etapa do funil, via triggers de INSERT e UPDATE em `projects.pipeline_stage` (pendência técnica registrada no item 129).
     - **Migration 027**: escrita em `projects` liberada pro módulo CRM (necessário pro drag-and-drop mover `pipeline_stage` de projetos que não são do usuário logado).
     - **Migration 028**: campos jurídicos em `clients` (`address`, `legal_rep_name`/`cpf`/`role`) + `contracts.signed_date`.
     - **Migration 029**: função `close_deal()` — fechamento de negócio atômico (atualiza cliente, cria SPE, gera contrato a partir da proposta, marca proposta aceita, projeto `fechado_ganho`), `security definer` com checagem de permissão interna.
     - **Tela inicial (home) pós-login**: saudação, data por extenso, grid de módulos filtrado por `profile_modules`, mural e Espaço PMON estáticos (TODO pra versão dinâmica futura).
     - **Dashboard CRM** (`/crm`): 5 KPIs do mês, funil de vendas, ranking por owner (Diego/Murillo).
     - **Pipeline** (`/crm/pipeline`): board kanban por `pipeline_stage`, criar novo prospect (cliente novo ou existente, código sugerido automaticamente), drag-and-drop nas 3 primeiras colunas (prospect/proposta/negociação — Fechado não aceita drop, só via botão dedicado).
     - **Aba "Comercial"** dentro da tela de projeto (visível só pra quem tem módulo CRM): criar proposta, mover pra negociação, marcar como perdido, e Fechar (ganho) completo — formulário de dados jurídicos do cliente + SPE + time responsável, chamando `close_deal()`.
     - **Filtro em `/projetos`** (Engenharia): só mostra projetos `fechado_ganho` ou legado (`pipeline_stage` null) — prospects/propostas/perdidos ficam só em `/crm/pipeline`.
128. **Decisões de arquitetura**:
     - Card do pipeline navega direto pra aba Comercial do projeto (não pra Visão Geral de Engenharia) — contexto certo vindo do CRM.
     - Código do contrato = número de versão da proposta (`lpad` 2 dígitos), não digitado manualmente.
     - `close_deal()` é uma função atômica no banco (não múltiplas chamadas do frontend) — evita escrita parcial se algo falhar no meio do fechamento.
129. **Bugs encontrados e corrigidos**:
     - `lib/api/crm.ts` teve `PIPELINE_STAGES` duplicado (import novo + declaração local antiga) numa tentativa de edição rejeitada que parcialmente aplicou — corrigido.
     - `frontend/app/(app)/page.tsx` precisou ser reescrito via terminal (`rm` + heredoc) depois de tentativas de Edit/Write concatenarem conteúdo antigo com novo repetidamente.
     - `close_deal()` (migration 029) inicialmente não tinha `contracts.signed_date` (coluna não existia ainda) — pego antes de aplicar, migration 028 ajustada.
     - Card do pipeline levava pra Visão Geral de Engenharia em vez da aba Comercial — corrigido (ver item 128).
     - `project_stage_history` (migration 026) quebra com `NotNullViolationError` se `pipeline_stage` for setado null via UPDATE — não corrigido por não ser caminho real do app hoje (guard sugerido: `if new.pipeline_stage is null then return new;`).
130. **Pendente / próximos passos**:
     - Reembolso (próximo módulo grande, ainda não iniciado).
     - Visual da tela inicial (home) — funcional mas não refinado.
     - Seed de `profile_modules` pros outros 5 (Murillo/Carlos/Weslley/Camila/Thiago) — só em produção quando as migrations forem aplicadas lá.
     - PR de `feature/clientes-crm` → `main` ainda não aberto (muitas migrations acumuladas: 011-029).
     - Trigger de `project_stage_history` não trata `pipeline_stage=null` em UPDATE (ver item 129).
131. **Não fazer ainda** (registrado explicitamente pelo usuário):
     - Não aplicar nenhuma migration em produção.
     - Não mergear `feature/clientes-crm` em `main`.
     - Não trocar a senha do banco de produção.

## Sessão 2026-07-10 — Arquitetura do módulo Financeiro (Folha PJ, Contas a Pagar/Receber, Documentos)

132. **Contexto**: revisão do Anexo I (planilha de apuração mensal real, 
     modelo usado hoje pra gerar a NF de colaboradores PJ como Camila) e 
     da aba DEPESAS do Controle_Portfólio_PMON.xlsx — achado crítico: o 
     campo "CENTRO DE CUSTO" da planilha real está 0% preenchido (0 de 
     1.734 linhas), nunca foi usado na prática; quem categoriza despesa 
     de fato é a coluna PROJETO (48% das linhas) + "00 PMON" como bucket 
     interno (32% das linhas). Isso motivou a revisão completa do 
     desenho de centro de custo feito na sessão anterior.

133. **Princípio arquitetural adotado** (validado por pesquisa em 
     multidimensional accounting — Dynamics 365, Sage Intacct — e prática 
     de DRE gerencial brasileira): toda despesa carrega duas dimensões 
     independentes, nunca uma no lugar da outra — Categoria (natureza: 
     "o que é") e Projeto (job: "pra quem foi", nullable). Rateio por 
     time (Carlos/Weslley/Diego-Murillo) é uma terceira dimensão 
     ortogonal, via regra nomeada e reutilizável.

134. **Dois mecanismos de remuneração coexistem, não confundir**:
     - Sócios (Carlos, Weslley, Diego, Murillo): distribuição de lucro 
       por portfólio (15% mensal / 35% pool de investimento único da 
       PMON / 50% pool combinado Diego+Murillo, split manual entre os 
       dois no ato).
     - Colaboradores PJ (Camila, Thiago): remuneração fixa por projeto + 
       reembolsos aprovados do período + pró-labore mínimo — modelo do 
       Anexo I, com aditivo contratual quando o valor muda.

135. **Schema desenhado (não implementado ainda — só arquitetura)**:
     - `expense_categories` (renomeia `cost_centers` de ontem) — 
       categoria/natureza da despesa, com hierarquia opcional 
       (parent_category_id).
     - `allocation_rules` + `allocation_rule_splits` — generaliza e 
       substitui `team_cost_allocations` (de ontem): regras de rateio 
       nomeadas e editáveis numa tela central (junto com cadastro de 
       usuários/privilégios), escolhidas no momento do lançamento (não 
       inferidas automaticamente, exceto Reembolso que continua 
       escolhendo sozinho por trás dos panos com base em quem lançou). 
       Cada lançamento grava o `allocation_rule_id` vigente no momento — 
       mudar a regra depois não altera lançamentos passados, só os 
       futuros.
     - `expenses` (despesas gerais, nova) — category_id, project_id 
       (nullable), vendor_name, competencia_month (regime de 
       competência) + due_date/payment_date (regime de caixa), value, 
       allocation_rule_id, status.
     - `contract_scopes` (dentro de `contracts`) e `proposal_scopes` 
       (dentro de `proposals`, nasce desde a negociação) — resolve o 
       caso "1 contrato, 1 NF única, múltiplos serviços indo pra 
       portfólios diferentes" (ex: The Gardens: Gerenciamento de Prazo → 
       Carlos, Gerenciamento de Custo → Diego). Divisão de receita por 
       escopo numa parcela é calculada no relatório, não gravada em 
       tabela nova.
     - `contract_installments` — parcelas projetadas na criação do 
       contrato (não mês a mês), com `is_revision_point` marcando onde 
       cai o aniversário de reajuste INCC; ao confirmar reajuste, só as 
       parcelas futuras recalculam, passadas ficam como histórico.
     - `vendor_contracts` (generaliza o que seria `service_intake_contracts`) 
       — cobre aluguel, contabilidade, e contratos de tomada de serviço 
       PJ (Camila/Thiago) na mesma base: vendor_name, cnpj, contract_type, 
       category_id, monthly_value, vigência, withholding_percentage 
       (nullable — retenção de IR, ex: aluguel).
     - `vendor_contract_amendments` — histórico de aditivo (mudança de 
       valor), mesmo padrão de vigência já usado em outras tabelas do 
       sistema.
     - `personnel_contract_details` — só quando contract_type='pessoal_pj', 
       vincula o vendor_contract a um profile_id (a pessoa).
     - `vendor_contract_installments` — espelho de `contract_installments` 
       do lado da despesa: pré-lançamento de despesas recorrentes futuras 
       (aluguel, contabilidade, PJ) pra permitir a mesma projeção anual 
       de fluxo de caixa que já existe do lado da receita.
     - Retenção de imposto (ex: DARF IRRF sobre aluguel): 1 lançamento 
       de despesa com withholding_percentage gera automaticamente 2 
       linhas em `expenses` — o valor líquido pro fornecedor e o valor 
       retido pra Receita Federal (categoria própria, vencimento no dia 
       do DARF).
     - Documentos: Google Drive pessoal (pmongerenciamento@gmail.com, 
       Google One 1TB) como camada de armazenamento de arquivos gerados 
       pelo sistema (NF, boleto, comprovante, e futuramente MS Project/
       fotos/planilhas também) — via OAuth pessoal (não Workspace), 
       escopo de permissão restrito a `drive.file` (só arquivos que o 
       app cria), tela de consentimento em modo Teste. Risco assumido 
       conscientemente: integração atrelada à conta pessoal do Diego, 
       não a uma conta corporativa.

136. **Fluxo de aprovação da Folha PJ**: demonstrativo mensal (projeto + 
     reembolso aprovado + pró-labore mínimo + comissões/deduções manuais) 
     só é gerado depois que TODOS os reembolsos do período estiverem 
     aprovados — bloqueia até resolver pendência, não gera com aviso.

137. **Decisões de nomenclatura**: `contracts` = contrato de prestação de 
     serviço (PMON → cliente, receita). `vendor_contracts` = contrato de 
     tomada de serviço (fornecedor/PJ → PMON, despesa). Nomes 
     propositalmente diferentes pra evitar confusão futura entre os 
     dois sentidos jurídicos opostos.

138. **Comissões e Deduções** (campos do Anexo I hoje sempre zerados): 
     ficam como campo de ajuste manual (descrição + valor) no 
     demonstrativo, sem tabela própria — raramente usados na prática.

139. **Pendências técnicas identificadas, não bloqueantes**:
     - Arredondamento em divisão percentual entre escopos: o último 
       escopo deve absorver a sobra de centavo, pra soma das partes 
       sempre bater com o total exato.
     - Confirmar com o contador se o percentual de retenção de IR do 
       contrato de aluguel específico da PMON bate com a regra padrão da 
       Receita antes de automatizar o cálculo.

140. **Nada disso foi implementado ainda** — sessão inteira foi de 
     arquitetura/discussão, sem nenhuma migration ou código novo. 
     Próximo passo será começar a implementação a partir deste desenho, 
     em ordem a definir na próxima sessão.
