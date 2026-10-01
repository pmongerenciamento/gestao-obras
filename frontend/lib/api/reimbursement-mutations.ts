import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import type { NewItemInput, NewReportInput } from "@/types/reimbursement";

// Só client-side (mesmo padrão de lib/api/project-mutations.ts / proposal-mutations.ts).
// profile_id não é parâmetro: resolvido aqui via sessão, e a RLS de
// reimbursement_reports (profile_id = auth.uid()) já rejeita qualquer valor
// divergente de qualquer forma.

async function getCurrentUserId(): Promise<string> {
  const supabase = createSupabaseClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) throw new Error("Sessão expirada.");
  return user.id;
}

export async function createReport(input: NewReportInput): Promise<string> {
  const supabase = createSupabaseClient();
  const profileId = await getCurrentUserId();

  const { data, error } = await supabase
    .from("reimbursement_reports")
    .insert({
      profile_id: profileId,
      period_start: input.periodStart,
      period_end: input.periodEnd,
      status: "rascunho",
    })
    .select("id")
    .single();

  if (error) throw error;
  if (!data) throw new Error("Falha ao criar o relatório.");

  return data.id;
}

export async function createItem(reportId: string, input: NewItemInput): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase.from("reimbursement_items").insert({
    report_id: reportId,
    type: input.type,
    project_id: input.projectId || null,
    cost_center_id: input.costCenterId || null,
    expense_date: input.expenseDate,
    description: input.description,
    km_traveled: input.kmTraveled ?? null,
    km_rate: input.kmRate ?? null,
    toll_amount: input.tollAmount ?? 0,
    other_amount: input.otherAmount ?? 0,
    requires_preapproval: input.requiresPreapproval,
    total_amount: input.totalAmount,
  });

  if (error) throw error;
}

export async function submitForApproval(reportId: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "enviado" })
    .eq("id", reportId);

  if (error) throw error;
}

// Tela /reembolso/aprovacoes: RLS (reimbursement_reports_approve, 030) só
// deixa passar quem tem has_permission('reimbursement_reports','write').
export async function approveReport(reportId: string): Promise<void> {
  const supabase = createSupabaseClient();
  const approverId = await getCurrentUserId();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "aprovado", approved_by: approverId, approved_at: new Date().toISOString() })
    .eq("id", reportId);

  if (error) throw error;
}

export async function rejectReport(reportId: string, reason: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "rejeitado", rejection_reason: reason })
    .eq("id", reportId);

  if (error) throw error;
}

// "Corrigir e reenviar": volta um relatório rejeitado pra rascunho, editável
// de novo. RLS (reimbursement_reports_update_own_draft, ajustada em
// 032_reimbursement_reopen_rejected.sql) só deixa o próprio dono fazer isso
// partindo de status='rejeitado'. Limpa rejection_reason — senão o motivo da
// rejeição anterior fica pendurado e confunde numa próxima rejeição.
export async function reopenReport(reportId: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "rascunho", rejection_reason: null })
    .eq("id", reportId);

  if (error) throw error;
}
