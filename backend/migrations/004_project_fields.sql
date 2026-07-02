-- Migration: 004_project_fields
-- Adiciona os campos de cadastro do projeto (cliente, localização, tipologia,
-- métricas de obra, orçamento e imagem) usados pelo formulário "Novo projeto".
-- Referência: docs/referencia-projeto.md (seção 5.1, módulo de Importação/cadastro)

-- =========================================================
-- IDENTIFICAÇÃO E LOCALIZAÇÃO
-- =========================================================

alter table projects add column client_name text;
alter table projects add column city text;
alter table projects add column state text
    check (state is null or char_length(state) = 2);

-- =========================================================
-- TIPOLOGIA
-- =========================================================

alter table projects add column tipologia_obra text
    check (tipologia_obra is null or tipologia_obra in (
        'residencial_vertical',
        'comercial_vertical',
        'unifamiliar',
        'galpao_industrial',
        'loteamento'
    ));

alter table projects add column tipologia_construtiva text
    check (tipologia_construtiva is null or tipologia_construtiva in (
        'alvenaria_estrutural',
        'concreto_armado',
        'pre_fabricado',
        'infraestrutura',
        'parede_concreto',
        'outros'
    ));

-- Preenchido só quando tipologia_construtiva = 'outros'
alter table projects add column tipologia_construtiva_outros text;

-- =========================================================
-- MÉTRICAS DE OBRA
-- num_torres/num_pavimentos/num_unidades fazem sentido só para tipologia_obra
-- vertical (residencial_vertical/comercial_vertical); num_lotes só para
-- loteamento. Não há CHECK cruzado aqui — a UI controla quais campos exibir
-- por tipologia (ver plano do formulário); o banco só guarda os valores.
-- =========================================================

alter table projects add column num_torres integer;
alter table projects add column num_pavimentos integer;
alter table projects add column num_unidades integer;
alter table projects add column num_lotes integer;
alter table projects add column area_construida numeric;
alter table projects add column area_privativa numeric;

-- =========================================================
-- ORÇAMENTO E PRAZO
-- =========================================================

alter table projects add column orcamento numeric;
alter table projects add column data_base_orcamento date;
alter table projects add column prazo_estimado_meses integer;

-- =========================================================
-- IMAGEM (perspectiva 3D do empreendimento)
-- =========================================================

alter table projects add column image_url text;
