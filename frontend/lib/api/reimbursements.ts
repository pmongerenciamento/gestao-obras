import type {
  CostCenter,
  ProjectOption,
  RateRule,
  ReimbursementItem,
  ReimbursementItemType,
  ReimbursementReport,
  ReimbursementReportStatus,
} from "@/types/reimbursement";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura do módulo Reembolso (backend/migrations/030_create_reimbursements.sql).
// Reembolso não segue o sistema de permissões por módulo — é aberto a
// qualquer funcionário autenticado. RLS de reimbursement_reports/items já
// restringe cada usuário aos próprios relatórios (profile_id = auth.uid()),
// então não filtramos por usuário aqui de novo.

interface ReportRow {
  id: string;
  profile_id: string;
  period_start: string;
  period_end: string;
  status: string;
  rejection_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  reimbursement_items: { total_amount: number }[];
}

export interface ReportWithTotal extends ReimbursementReport {
  total: number;
}

export interface PendingApprovalReport extends ReimbursementReport {
  total: number;
  requesterName: string;
}

function mapReportRow(row: ReportRow): ReportWithTotal {
  return {
    id: row.id,
    profileId: row.profile_id,
    periodStart: row.period_start,
    periodEnd: row.period_end,
    status: row.status as ReimbursementReportStatus,
    rejectionReason: row.rejection_reason,
    approvedBy: row.approved_by,
    approvedAt: row.approved_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    total: row.reimbursement_items.reduce((sum, item) => sum + Number(item.total_amount), 0),
  };
}

export async function listMyReports(): Promise<ReportWithTotal[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("reimbursement_reports")
    .select(
      "id, profile_id, period_start, period_end, status, rejection_reason, approved_by, approved_at, created_at, updated_at, reimbursement_items(total_amount)",
    )
    .order("created_at", { ascending: false });

  if (error || !data) return [];
  return (data as unknown as ReportRow[]).map(mapReportRow);
}

// Fila do financeiro (backend/migrations/030): todos os relatórios 'enviado'
// de qualquer usuário — RLS (reimbursement_reports_own) já libera essa
// leitura ampla pra quem tem has_permission('reimbursement_reports','read').
// Mais antigos primeiro, pra priorizar quem está esperando há mais tempo.
export async function listPendingApprovals(): Promise<PendingApprovalReport[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("reimbursement_reports")
    .select(
      "id, profile_id, period_start, period_end, status, rejection_reason, approved_by, approved_at, created_at, updated_at, reimbursement_items(total_amount)",
    )
    .eq("status", "enviado")
    .order("created_at", { ascending: true });

  if (error || !data) return [];

  const rows = data as unknown as ReportRow[];
  const profileIds = Array.from(new Set(rows.map((r) => r.profile_id)));
  const nameEntries = await Promise.all(
    profileIds.map(async (profileId) => {
      const { data: displayName } = await supabase.rpc("profile_display_name", { p_profile_id: profileId });
      return [profileId, (displayName as string | null) ?? "—"] as const;
    }),
  );
  const nameByProfileId = new Map(nameEntries);

  return rows.map((row) => ({
    ...mapReportRow(row),
    requesterName: nameByProfileId.get(row.profile_id) ?? "—",
  }));
}

export async function getReport(reportId: string): Promise<ReimbursementReport | null> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("reimbursement_reports")
    .select(
      "id, profile_id, period_start, period_end, status, rejection_reason, approved_by, approved_at, created_at, updated_at",
    )
    .eq("id", reportId)
    .maybeSingle();

  if (error || !data) return null;
  return {
    id: data.id,
    profileId: data.profile_id,
    periodStart: data.period_start,
    periodEnd: data.period_end,
    status: data.status as ReimbursementReportStatus,
    rejectionReason: data.rejection_reason,
    approvedBy: data.approved_by,
    approvedAt: data.approved_at,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

interface ItemRow {
  id: string;
  report_id: string;
  type: string;
  project_id: string | null;
  cost_center_id: string | null;
  expense_date: string;
  description: string;
  km_traveled: number | null;
  km_rate: number | null;
  toll_amount: number;
  other_amount: number;
  requires_preapproval: boolean;
  total_amount: number;
  projects: { name: string } | null;
  cost_centers: { name: string } | null;
}

function mapItemRow(row: ItemRow): ReimbursementItem {
  return {
    id: row.id,
    reportId: row.report_id,
    type: row.type as ReimbursementItemType,
    projectId: row.project_id,
    projectName: row.projects?.name ?? null,
    costCenterId: row.cost_center_id,
    costCenterName: row.cost_centers?.name ?? null,
    expenseDate: row.expense_date,
    description: row.description,
    kmTraveled: row.km_traveled !== null ? Number(row.km_traveled) : null,
    kmRate: row.km_rate !== null ? Number(row.km_rate) : null,
    tollAmount: Number(row.toll_amount),
    otherAmount: Number(row.other_amount),
    requiresPreapproval: row.requires_preapproval,
    totalAmount: Number(row.total_amount),
  };
}

export async function listReportItems(reportId: string): Promise<ReimbursementItem[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("reimbursement_items")
    .select(
      "id, report_id, type, project_id, cost_center_id, expense_date, description, km_traveled, km_rate, toll_amount, other_amount, requires_preapproval, total_amount, projects(name), cost_centers(name)",
    )
    .eq("report_id", reportId)
    .order("expense_date", { ascending: false });

  if (error || !data) return [];
  return (data as unknown as ItemRow[]).map(mapItemRow);
}

export async function listCostCenters(): Promise<CostCenter[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("cost_centers").select("id, name").order("name");

  if (error || !data) return [];
  return data;
}

// Só as taxas vigentes (sem data de fim) — a mesma regra usada pelo cálculo
// de total no formulário de item.
export async function listActiveRateRules(): Promise<RateRule[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("reimbursement_rate_rules")
    .select("id, type, value, unit, effective_start_date, effective_end_date")
    .is("effective_end_date", null);

  if (error || !data) return [];
  return data.map((row) => ({
    id: row.id,
    type: row.type as ReimbursementItemType,
    value: Number(row.value),
    unit: row.unit,
    effectiveStartDate: row.effective_start_date,
    effectiveEndDate: row.effective_end_date,
  }));
}

// Lista aberta (migration 031_projects_read_open.sql) — qualquer usuário
// autenticado, independente de módulo, pra alimentar o select de projeto no
// item "Visita a Cliente"/"Visita Comercial".
export async function listProjectsForSelect(): Promise<ProjectOption[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("projects").select("id, name").order("name");

  if (error || !data) return [];
  return data;
}
