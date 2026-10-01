import type { PaymentType, Proposal, ProposalStatus, ServiceType } from "@/types/proposal";
import type { PipelineStage } from "@/types/crm";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura da aba Comercial (backend/migrations/022_create_proposals.sql). RLS:
// proposals_read (has_permission('proposals','read')) e service_types_read
// (has_permission('service_types','read')) já liberam pro módulo CRM.

interface ProposalRow {
  id: string;
  project_id: string;
  version: number;
  service_type_id: string | null;
  value: number;
  payment_type: string;
  installments_count: number | null;
  scope_description: string | null;
  status: string;
  valid_until: string | null;
  lost_reason: string | null;
  service_types: { name: string } | null;
}

function mapRow(row: ProposalRow): Proposal {
  return {
    id: row.id,
    projectId: row.project_id,
    version: row.version,
    serviceTypeId: row.service_type_id,
    serviceTypeName: row.service_types?.name ?? null,
    value: Number(row.value),
    paymentType: row.payment_type as PaymentType,
    installmentsCount: row.installments_count,
    scopeDescription: row.scope_description,
    status: row.status as ProposalStatus,
    validUntil: row.valid_until,
    lostReason: row.lost_reason,
  };
}

export async function getLatestProposal(projectId: string): Promise<Proposal | null> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("proposals")
    .select(
      "id, project_id, version, service_type_id, value, payment_type, installments_count, scope_description, status, valid_until, lost_reason, service_types(name)",
    )
    .eq("project_id", projectId)
    .order("version", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error || !data) return null;
  return mapRow(data as unknown as ProposalRow);
}

export async function listServiceTypes(): Promise<ServiceType[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("service_types").select("id, code, name").order("code");

  if (error || !data) return [];
  return data;
}

export async function getProjectPipelineStage(projectId: string): Promise<PipelineStage | null> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("projects")
    .select("pipeline_stage")
    .eq("id", projectId)
    .maybeSingle();

  if (error || !data) return null;
  return (data.pipeline_stage as PipelineStage | null) ?? "prospect";
}
