import type { PipelineStage } from "@/types/crm";

export interface PipelineCardData {
  id: string;
  name: string;
  clientName: string | null; // null -> "Sem cliente vinculado" na UI
  ownerId: string;
  ownerDisplayName: string;
  pipelineStage: PipelineStage;
  daysInStage: number | null; // prospect/negociacao
  proposalValidUntil: string | null; // proposta — "YYYY-MM-DD"
  proposalValidUntilExpired: boolean;
  lostReason: string | null; // fechado_perdido
}

export interface PipelineColumn {
  stage: PipelineStage;
  label: string;
  cards: PipelineCardData[];
}
