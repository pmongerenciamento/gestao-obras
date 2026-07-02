export interface ProjectMember {
  id: string;
  name: string;
  avatarUrl?: string;
}

export type ProjectStatus = "em_andamento" | "pausado" | "concluido";

export interface ProjectSummary {
  id: string;
  name: string;
  clientName: string;
  city: string;
  imageUrl: string | null;
  lastSnapshotAt: string | null;
  status: ProjectStatus;
  members: ProjectMember[];
}

export interface ProjectDetail extends ProjectSummary {
  startDate: string | null;
  baselineFinish: string | null;
  forecastFinish: string | null;
}

// Valores espelham os CHECK constraints de backend/migrations/004_project_fields.sql
export type TipologiaObra =
  | "residencial_vertical"
  | "comercial_vertical"
  | "unifamiliar"
  | "galpao_industrial"
  | "loteamento";

export type TipologiaConstrutiva =
  | "alvenaria_estrutural"
  | "concreto_armado"
  | "pre_fabricado"
  | "infraestrutura"
  | "parede_concreto"
  | "outros";

export const TIPOLOGIA_OBRA_OPTIONS: { value: TipologiaObra; label: string }[] = [
  { value: "residencial_vertical", label: "Residencial vertical" },
  { value: "comercial_vertical", label: "Comercial vertical" },
  { value: "unifamiliar", label: "Unifamiliar" },
  { value: "galpao_industrial", label: "Galpão industrial" },
  { value: "loteamento", label: "Loteamento" },
];

export const TIPOLOGIA_CONSTRUTIVA_OPTIONS: { value: TipologiaConstrutiva; label: string }[] = [
  { value: "alvenaria_estrutural", label: "Alvenaria estrutural" },
  { value: "concreto_armado", label: "Concreto armado" },
  { value: "pre_fabricado", label: "Pré-fabricado" },
  { value: "infraestrutura", label: "Infraestrutura" },
  { value: "parede_concreto", label: "Parede de concreto" },
  { value: "outros", label: "Outros" },
];

export const VERTICAL_TIPOLOGIAS: TipologiaObra[] = ["residencial_vertical", "comercial_vertical"];

export interface NewProjectInput {
  name: string;
  clientName: string;
  city: string;
  state: string;
  tipologiaObra: TipologiaObra;
  tipologiaConstrutiva: TipologiaConstrutiva;
  tipologiaConstrutivaOutros?: string;
  numTorres?: number;
  numPavimentos?: number;
  numUnidades?: number;
  numLotes?: number;
  areaConstruida?: number;
  areaPrivativa?: number;
  orcamento?: number;
  dataBaseOrcamento?: string;
  prazoEstimadoMeses?: number;
  imageUrl?: string | null;
}
