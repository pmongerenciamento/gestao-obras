import type { CrmDashboardData, FunnelStage, RankingEntry } from "@/types/crm";
import { PIPELINE_STAGES } from "@/lib/pipeline-stages";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Dashboard do módulo CRM: KPIs do mês corrente + funil de vendas (foto do
// estado atual, sem filtro de período) + ranking do período. RLS libera
// leitura de `projects` e `proposals` pra quem tem o módulo 'crm'
// (backend/migrations/024_projects_read_crm.sql, 023_create_permission_catalog.sql);
// profile_display_name (025) resolve o nome de quem recebe a proposta aceita
// (full_name, com fallback pro e-mail) sem expor auth.users direto.
//
// "Aceita no mês" (taxa de conversão, ticket médio, ranking) usa
// proposals.signed_date — é o único campo que representa de fato a data em
// que a proposta virou aceita/assinada (status é só um estado, sem data
// própria). "Propostas enviadas" usa sent_date, "prospects novos" usa
// projects.created_at.

const TIMEZONE_OFFSET = "-03:00"; // America/Sao_Paulo não observa horário de verão desde 2019

interface MonthRange {
  startDate: string; // "YYYY-MM-DD" — pra colunas `date` (sent_date, signed_date)
  endDate: string; // primeiro dia do mês seguinte, exclusivo
  startTimestamp: string; // ISO com offset — pra colunas `timestamptz` (created_at)
  endTimestamp: string;
}

function getCurrentMonthRange(): MonthRange {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());

  const year = Number(parts.find((p) => p.type === "year")!.value);
  const month = Number(parts.find((p) => p.type === "month")!.value);
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;

  const pad = (n: number) => String(n).padStart(2, "0");
  const startDate = `${year}-${pad(month)}-01`;
  const endDate = `${nextYear}-${pad(nextMonth)}-01`;

  return {
    startDate,
    endDate,
    startTimestamp: `${startDate}T00:00:00${TIMEZONE_OFFSET}`,
    endTimestamp: `${endDate}T00:00:00${TIMEZONE_OFFSET}`,
  };
}

interface ProjectStageRow {
  pipeline_stage: string | null;
}

interface ProposalValueRow {
  value: number;
}

interface RankingRawRow {
  value: number;
  projects: { owner_id: string } | null;
}

export async function getCrmDashboardData(): Promise<CrmDashboardData> {
  const supabase = await createSupabaseServerClient();
  const { startDate, endDate, startTimestamp, endTimestamp } = getCurrentMonthRange();

  const [
    novosProspectsResult,
    funnelRowsResult,
    propostasEnviadasResult,
    aceitasNoMesResult,
    emNegociacaoResult,
    rankingRowsResult,
  ] = await Promise.all([
    supabase
      .from("projects")
      .select("id", { count: "exact", head: true })
      .eq("pipeline_stage", "prospect")
      .gte("created_at", startTimestamp)
      .lt("created_at", endTimestamp),
    supabase.from("projects").select("pipeline_stage"),
    supabase
      .from("proposals")
      .select("id", { count: "exact", head: true })
      .gte("sent_date", startDate)
      .lt("sent_date", endDate),
    supabase
      .from("proposals")
      .select("value")
      .eq("status", "aceita")
      .gte("signed_date", startDate)
      .lt("signed_date", endDate),
    supabase.from("proposals").select("value").eq("status", "em_negociacao"),
    supabase
      .from("proposals")
      .select("value, projects(owner_id)")
      .eq("status", "aceita")
      .gte("signed_date", startDate)
      .lt("signed_date", endDate),
  ]);

  const novosProspects = novosProspectsResult.count ?? 0;
  const propostasEnviadas = propostasEnviadasResult.count ?? 0;

  const aceitasNoMesRows = (aceitasNoMesResult.data ?? []) as ProposalValueRow[];
  const aceitasNoMesCount = aceitasNoMesRows.length;
  const taxaConversao = propostasEnviadas > 0 ? aceitasNoMesCount / propostasEnviadas : null;
  const ticketMedio =
    aceitasNoMesCount > 0
      ? aceitasNoMesRows.reduce((sum, row) => sum + Number(row.value), 0) / aceitasNoMesCount
      : null;

  const emNegociacaoRows = (emNegociacaoResult.data ?? []) as ProposalValueRow[];
  const emNegociacaoCount = emNegociacaoRows.length;
  const emNegociacaoValue = emNegociacaoRows.reduce((sum, row) => sum + Number(row.value), 0);

  const funnelCounts = new Map<string, number>();
  for (const row of (funnelRowsResult.data ?? []) as ProjectStageRow[]) {
    const stage = row.pipeline_stage ?? "prospect";
    funnelCounts.set(stage, (funnelCounts.get(stage) ?? 0) + 1);
  }
  const funnel: FunnelStage[] = PIPELINE_STAGES.map(({ stage, label }) => ({
    stage,
    label,
    count: funnelCounts.get(stage) ?? 0,
  }));

  const rankingByOwner = new Map<string, { count: number; totalValue: number }>();
  for (const row of (rankingRowsResult.data ?? []) as unknown as RankingRawRow[]) {
    const ownerId = row.projects?.owner_id;
    if (!ownerId) continue;
    const entry = rankingByOwner.get(ownerId) ?? { count: 0, totalValue: 0 };
    entry.count += 1;
    entry.totalValue += Number(row.value);
    rankingByOwner.set(ownerId, entry);
  }

  const ranking: RankingEntry[] = await Promise.all(
    Array.from(rankingByOwner.entries()).map(async ([ownerId, { count, totalValue }]) => {
      const { data: displayName } = await supabase.rpc("profile_display_name", {
        p_profile_id: ownerId,
      });
      return { ownerId, displayName: (displayName as string | null) ?? "—", count, totalValue };
    }),
  );
  ranking.sort((a, b) => b.totalValue - a.totalValue);

  return {
    kpis: {
      novosProspects,
      propostasEnviadas,
      taxaConversao,
      ticketMedio,
      emNegociacaoCount,
      emNegociacaoValue,
    },
    funnel,
    ranking,
  };
}
