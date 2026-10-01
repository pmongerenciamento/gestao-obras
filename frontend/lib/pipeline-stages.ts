import type { PipelineStage } from "@/types/crm";

// Compartilhado entre o funil do dashboard CRM (lib/api/crm.ts) e o board de
// pipeline (lib/api/pipeline.ts) — mesmas 5 etapas, mesmos rótulos.
export const PIPELINE_STAGES: { stage: PipelineStage; label: string }[] = [
  { stage: "prospect", label: "Prospect" },
  { stage: "proposta", label: "Proposta" },
  { stage: "negociacao", label: "Negociação" },
  { stage: "fechado_ganho", label: "Fechado (ganho)" },
  { stage: "fechado_perdido", label: "Fechado (perdido)" },
];
