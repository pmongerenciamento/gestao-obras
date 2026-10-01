import type { PipelineCardData, PipelineColumn } from "@/types/pipeline";
import type { PipelineStage } from "@/types/crm";
import { PIPELINE_STAGES } from "@/lib/pipeline-stages";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Board do pipeline de vendas: 1 coluna por pipeline_stage, com dados
// contextuais por card (dias na etapa via project_stage_history, validade da
// proposta, motivo de perda). RLS libera leitura de projects/proposals/clients
// pra quem tem o módulo 'crm' (migrations 023/024); profile_display_name (025)
// resolve o nome do owner sem expor auth.users.

interface ProjectRow {
  id: string;
  name: string;
  client_id: string | null;
  owner_id: string;
  pipeline_stage: string | null;
}

interface ClientRow {
  id: string;
  legal_name: string;
}

interface StageHistoryRow {
  project_id: string;
  entered_at: string;
}

interface ProposalRow {
  project_id: string;
  version: number;
  status: string;
  valid_until: string | null;
  lost_reason: string | null;
}

function daysSince(iso: string): number {
  const ms = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

// "YYYY-MM-DD" em America/Sao_Paulo, pra comparar com valid_until (coluna
// `date`, sem timezone) do mesmo jeito que o resto do dashboard CRM.
function todayDateBR(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
}

export async function getPipelineBoard(): Promise<PipelineColumn[]> {
  const supabase = await createSupabaseServerClient();

  const [projectsResult, historyResult, proposalsResult] = await Promise.all([
    supabase.from("projects").select("id, name, client_id, owner_id, pipeline_stage"),
    supabase.from("project_stage_history").select("project_id, entered_at").is("exited_at", null),
    supabase.from("proposals").select("project_id, version, status, valid_until, lost_reason"),
  ]);

  const projects = (projectsResult.data ?? []) as ProjectRow[];
  const openStageRows = (historyResult.data ?? []) as StageHistoryRow[];
  const proposalRows = (proposalsResult.data ?? []) as ProposalRow[];

  const clientIds = Array.from(
    new Set(projects.map((p) => p.client_id).filter((id): id is string => Boolean(id))),
  );
  const clientsResult = clientIds.length
    ? await supabase.from("clients").select("id, legal_name").in("id", clientIds)
    : { data: [] as ClientRow[] };
  const clientNameById = new Map(((clientsResult.data ?? []) as ClientRow[]).map((c) => [c.id, c.legal_name]));

  const ownerIds = Array.from(new Set(projects.map((p) => p.owner_id)));
  const ownerNameEntries = await Promise.all(
    ownerIds.map(async (ownerId) => {
      const { data } = await supabase.rpc("profile_display_name", { p_profile_id: ownerId });
      return [ownerId, (data as string | null) ?? "—"] as const;
    }),
  );
  const ownerNameById = new Map(ownerNameEntries);

  const openStageByProject = new Map(openStageRows.map((r) => [r.project_id, r.entered_at]));

  // Por projeto: última proposal não-recusada (maior version) e última recusada (maior version)
  const latestNonRecusadaByProject = new Map<string, ProposalRow>();
  const latestRecusadaByProject = new Map<string, ProposalRow>();
  for (const row of proposalRows) {
    const target = row.status === "recusada" ? latestRecusadaByProject : latestNonRecusadaByProject;
    const current = target.get(row.project_id);
    if (!current || row.version > current.version) target.set(row.project_id, row);
  }

  const today = todayDateBR();

  const cards: PipelineCardData[] = projects.map((project) => {
    const stage = (project.pipeline_stage ?? "prospect") as PipelineStage;
    const enteredAt = openStageByProject.get(project.id) ?? null;

    let daysInStage: number | null = null;
    if ((stage === "prospect" || stage === "negociacao") && enteredAt) {
      daysInStage = daysSince(enteredAt);
    }

    let proposalValidUntil: string | null = null;
    let proposalValidUntilExpired = false;
    if (stage === "proposta") {
      const proposal = latestNonRecusadaByProject.get(project.id);
      if (proposal?.valid_until) {
        proposalValidUntil = proposal.valid_until;
        proposalValidUntilExpired = proposal.valid_until < today;
      }
    }

    let lostReason: string | null = null;
    if (stage === "fechado_perdido") {
      lostReason = latestRecusadaByProject.get(project.id)?.lost_reason ?? null;
    }

    return {
      id: project.id,
      name: project.name,
      clientName: project.client_id ? (clientNameById.get(project.client_id) ?? null) : null,
      ownerId: project.owner_id,
      ownerDisplayName: ownerNameById.get(project.owner_id) ?? "—",
      pipelineStage: stage,
      daysInStage,
      proposalValidUntil,
      proposalValidUntilExpired,
      lostReason,
    };
  });

  return PIPELINE_STAGES.map(({ stage, label }) => ({
    stage,
    label,
    cards: cards.filter((c) => c.pipelineStage === stage),
  }));
}
