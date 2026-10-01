export type PipelineStage = "prospect" | "proposta" | "negociacao" | "fechado_ganho" | "fechado_perdido";

export interface CrmKpis {
  novosProspects: number;
  propostasEnviadas: number;
  taxaConversao: number | null; // null = propostasEnviadas é 0, UI mostra "—"
  ticketMedio: number | null; // null = nenhuma proposta aceita no mês, UI mostra "—"
  emNegociacaoCount: number;
  emNegociacaoValue: number;
}

export interface FunnelStage {
  stage: PipelineStage;
  label: string;
  count: number;
}

export interface RankingEntry {
  ownerId: string;
  displayName: string;
  count: number;
  totalValue: number;
}

export interface CrmDashboardData {
  kpis: CrmKpis;
  funnel: FunnelStage[];
  ranking: RankingEntry[];
}
