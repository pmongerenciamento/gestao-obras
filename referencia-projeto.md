# Documento de Referência — Sistema de Gestão de Cronograma de Obras

> Última atualização: junho 2026  
> Status: em planejamento / pré-desenvolvimento

---

## 1. Visão Geral do Sistema

Sistema web de gestão de cronograma de obras com fonte de verdade no MS Project. Voltado para engenheiros de planejamento e gestores de obra que precisam de controle operacional contínuo — não apenas reporte pontual.

**Diferença central em relação a concorrentes (ex: Getsimplan):**  
Enquanto ferramentas existentes entregam um painel de apresentação, este sistema é o ambiente de trabalho diário do planejador — com histórico, versionamento, colaboração e múltiplas visões operacionais.

---

## 2. Stack Tecnológica Confirmada

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Backend | Python + FastAPI | Melhor ecossistema para lógica de cronograma, cálculo de caminho crítico e processamento de .mpp |
| Leitura de .mpp | MPXJ (biblioteca Python) | Lê formato binário nativo do MS Project sem necessidade de exportação |
| Frontend | Next.js + TypeScript + Tailwind | Moderno, tipado, deploy simples na Vercel |
| Banco de dados | Supabase (PostgreSQL) | Auth + DB + Storage em um lugar só |
| Autenticação | Supabase Auth | Login com senha, isolamento por conta |
| Armazenamento de arquivos | Supabase Storage | Guarda arquivos .mpp originais com histórico |
| Gráficos | D3.js | Flexibilidade total para Linha de Balanço e outros gráficos customizados |
| Hospedagem backend | Railway ou Render | Deploy de Python simples e barato |
| Hospedagem frontend | Vercel | Integração nativa com Next.js |
| Repositório | GitHub | Controle de versão + CI/CD |
| IDE / Execução | VS Code + Claude Code | Claude Code como agente de desenvolvimento; Claude.ai para arquitetura |

---

## 3. Recepção do Arquivo MS Project

### Princípio fundamental
O usuário nunca deve exportar, converter ou preparar o arquivo. Ele abre o sistema, arrasta o `.mpp` e o sistema faz todo o resto internamente.

### Formatos aceitos
| Formato | Suporte | Observação |
|---|---|---|
| `.mpp` | ✅ Primário | MS Project 2000–2019+, lido via MPXJ |
| `.xml` | ✅ Fallback | Exportação nativa do MS Project |
| `.xer` | ✅ Fallback | Formato Primavera P6 |
| `.xlsx` | ⚠️ Não recomendado | Perde vínculos e hierarquia WBS |

### Fluxo de importação
```
Usuário arrasta .mpp na interface
  → Frontend envia para backend via POST /upload
  → Backend processa via MPXJ
  → Sistema detecta: importação inicial ou atualização mensal?
  → Extrai estrutura (tarefas, WBS, vínculos) e progresso (datas, %)
  → Salva no banco via bulk insert
  → Arquivo original preservado no Supabase Storage
  → Frontend exibe confirmação com resumo do projeto importado
```

### Detecção automática de tipo de importação
- **Importação inicial:** nenhum projeto com mesmo nome/ID no banco → cria estrutura completa + baseline
- **Atualização mensal:** projeto existente detectado → cria novo snapshot, nunca sobrescreve baseline
- **Mudança estrutural:** sistema detecta novas tarefas ou vínculos → alerta o usuário e solicita confirmação antes de atualizar a estrutura

---

## 4. Modelo de Dados — Arquitetura de Versionamento

### Princípio: separar estrutura de progresso

```
projects
  └── tasks              ← estrutura (importada uma vez, raramente alterada)
  └── dependencies       ← vínculos entre tarefas
  └── snapshots          ← 1 por mês, imutáveis
        └── task_progress ← datas e % de cada tarefa naquele mês
```

### Tabelas principais

```sql
-- ESTRUTURA (quase nunca muda)
projects
  id, name, created_at, owner_id

tasks
  id, project_id, ms_uid, wbs, name, level, type, duration, is_milestone

dependencies
  id, project_id, predecessor_uid, successor_uid, type, lag_days

-- SNAPSHOTS MENSAIS (só datas e progresso)
snapshots
  id, project_id, reference_month, imported_at, file_url, is_baseline

task_progress
  id, snapshot_id, task_id,
  planned_start, planned_finish,     -- do baseline
  forecast_start, forecast_finish,   -- revisão do mês atual
  actual_start, actual_finish,       -- realizado
  percent_complete
```

### Regras de negócio do banco
- Baseline (`is_baseline = true`) é imutável após criação
- Cada importação mensal gera um novo snapshot — nunca sobrescreve
- Bulk insert obrigatório para projetos de 10–20 mil linhas
- Índices em `task_id`, `snapshot_id` e `project_id` para performance

---

## 5. Módulos do Sistema

### 5.1 Importação
- Upload drag-and-drop de .mpp
- Processamento automático via MPXJ
- Detecção de tipo (inicial / mensal / mudança estrutural)
- Resumo pós-importação (total de tarefas, período do projeto, % baseline)

### 5.2 Linha de Balanço
- Gráfico gerado com D3.js
- Eixo X: tempo; Eixo Y: pavimentos ou unidades construtivas
- Baseline vs realizado vs projetado
- Filtros por disciplina / equipe / pavimento

### 5.3 Gestão à Vista
Múltiplos quadros visuais:

**Quadro 1 — Matriz de atividades × pavimentos**
- Linhas: atividades (seleção filtrada do MS Project)
- Colunas: pavimentos
- Célula: data de início ou término (toggle)
- Cor da célula: mês da data (cada mês = uma cor fixa)
- Lógica de cores: todas as tarefas do mesmo mês recebem a mesma cor, facilitando leitura de ritmo de obra

*(outros quadros a detalhar em próxima etapa)*

### 5.4 Cronograma de Suprimentos
*(escopo a detalhar)*

### 5.5 Ambiente tipo Trello
- Cards baseados em atividades do cronograma
*(escopo a detalhar)*

### 5.6 Relatórios
- Export PDF dos painéis
- Export Excel/CSV dos dados
*(escopo a detalhar)*

---

## 6. Segurança e Privacidade

- Autenticação por e-mail e senha (Supabase Auth)
- Dados isolados por conta (row-level security no PostgreSQL)
- Criptografia em trânsito (TLS) e em repouso
- Conformidade LGPD
- Arquivo original preservado com histórico auditável (diferencial frente a concorrentes que apagam o arquivo)

---

## 7. Análise Competitiva — Getsimplan

**URL:** https://getsimplan.com  
**Status:** em validação (junho 2026)  
**Operador:** AM Inteligência e Planejamento Ltda., Curitiba/PR  
**Stack declarada:** Supabase + Cloudflare + Hostinger

### O que entregam
| Funcionalidade | Getsimplan | Nosso sistema |
|---|---|---|
| Upload .mpp direto | ✅ | ✅ |
| Curva S automática | ✅ | ✅ a implementar |
| Gantt base × real | ✅ | ✅ a implementar |
| Caminho Crítico | ✅ | ✅ a implementar |
| Diagnóstico DCMA (14 pontos) | ✅ | ⚠️ avaliar escopo |
| White-label (logo do cliente) | ✅ | ⚠️ avaliar escopo |
| Export PDF/Excel | ✅ | ✅ |
| **Linha de Balanço** | ❌ | ✅ diferencial |
| **Gestão à Vista** | ❌ | ✅ diferencial |
| **Cronograma de Suprimentos** | ❌ | ✅ diferencial |
| **Ambiente tipo Trello** | ❌ | ✅ diferencial |
| **Histórico mensal versionado** | ❌ | ✅ diferencial |
| **Arquivo original preservado** | ❌ (apagam) | ✅ diferencial |

### Posicionamento
- **Getsimplan:** ferramenta de reporte — gera painel bonito para apresentar ao cliente/fiscalização
- **Nosso sistema:** ferramenta de gestão operacional — ambiente de trabalho diário do engenheiro de planejamento

São produtos complementares, não excludentes. O nosso é mais profundo.

---

## 8. Decisões de Arquitetura Registradas

| Decisão | Escolha | Motivo |
|---|---|---|
| Formato de entrada | .mpp nativo | Evitar erro humano na exportação |
| Biblioteca de leitura | MPXJ (Python) | Único parser confiável para .mpp sem MS Project instalado |
| Versionamento | Snapshots mensais imutáveis | Baseline nunca sobrescrito; histórico auditável |
| Banco | PostgreSQL (Supabase) | Relacional para dados de cronograma; auth e storage integrados |
| Gráficos | D3.js | Flexibilidade total para visualizações customizadas de construção |
| IDE de desenvolvimento | VS Code + Claude Code | Claude Code como agente; Claude.ai para arquitetura |
| Deploy não usar | Lovable | Stack Python/FastAPI não suportada; teto para lógica complexa |

---

## 9. Próximos Passos

- [ ] Detalhar escopo dos módulos ainda abertos (Suprimentos, Trello, Relatórios)
- [ ] Obter arquivo .mpp de exemplo para mapear campos reais do MS Project
- [ ] Validar mapeamento MPXJ → schema do banco
- [ ] Configurar repositório GitHub
- [ ] Configurar projeto Supabase (banco + auth + storage)
- [ ] Iniciar desenvolvimento: módulo de importação (primeiro a ser construído)

---

*Este documento é vivo — deve ser atualizado a cada decisão relevante de arquitetura ou escopo.*
