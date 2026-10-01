import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import type { NewProposalInput } from "@/types/proposal";

// Só client-side (mesmo padrão de lib/api/pipeline-mutations.ts). Cada ação da
// aba Comercial escreve em 2 tabelas (proposals + projects.pipeline_stage)
// sequencialmente, sem transação real — mesmo risco não-transacional já
// aceito no resto do app.

export async function createProposal(projectId: string, input: NewProposalInput): Promise<void> {
  const supabase = createSupabaseClient();

  const { error: proposalError } = await supabase.from("proposals").insert({
    project_id: projectId,
    version: 1,
    status: "rascunho",
    service_type_id: input.serviceTypeId,
    value: input.value,
    payment_type: input.paymentType,
    installments_count: input.paymentType === "parcelado" ? (input.installmentsCount ?? null) : null,
    scope_description: input.scopeDescription || null,
    valid_until: input.validUntil || null,
  });
  if (proposalError) throw proposalError;

  const { error: projectError } = await supabase
    .from("projects")
    .update({ pipeline_stage: "proposta" })
    .eq("id", projectId);
  if (projectError) throw projectError;
}

export async function moveToNegotiation(proposalId: string, projectId: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error: proposalError } = await supabase
    .from("proposals")
    .update({ status: "em_negociacao" })
    .eq("id", proposalId);
  if (proposalError) throw proposalError;

  const { error: projectError } = await supabase
    .from("projects")
    .update({ pipeline_stage: "negociacao" })
    .eq("id", projectId);
  if (projectError) throw projectError;
}

export async function markAsLost(proposalId: string, projectId: string, lostReason: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error: proposalError } = await supabase
    .from("proposals")
    .update({ status: "recusada", lost_reason: lostReason })
    .eq("id", proposalId);
  if (proposalError) throw proposalError;

  const { error: projectError } = await supabase
    .from("projects")
    .update({ pipeline_stage: "fechado_perdido" })
    .eq("id", projectId);
  if (projectError) throw projectError;
}

// TODO próximo passo: "Fechar (ganho)" — proposal.status='aceita',
// projects.pipeline_stage='fechado_ganho', e provavelmente criar o contrato
// em `contracts` a partir da proposal aceita (ver backend/migrations/018_create_contracts.sql).
// Não implementado ainda, fora do escopo desta rodada.
