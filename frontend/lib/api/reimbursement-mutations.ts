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
  const profileId = await getCurrentUserId();

  // Rateio automático e invisível ao usuário (não vira campo no NewItemForm):
  // resolve a regra de rateio padrão do time de quem lançou, substituindo a
  // lógica antiga baseada em team_cost_allocations. A função
  // default_allocation_rule_for_profile (migration 035) devolve null se o
  // profile não tiver time — nesse caso grava null e o rateio fica a resolver.
  const { data: allocationRuleId, error: ruleError } = await supabase.rpc(
    "default_allocation_rule_for_profile",
    { p_profile_id: profileId },
  );

  if (ruleError) throw ruleError;

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
    allocation_rule_id: allocationRuleId ?? null,
  });

  if (error) throw error;
}

// As quatro mudanças de status abaixo usam .select("id").single(), mesmo padrão
// de updateProjectStage (pipeline-mutations.ts): a RLS filtra em silêncio as
// linhas que o usuário não pode alterar (0 linhas, sem erro de Postgres), e o
// .single() com 0 linhas devolvidas vira erro do PostgREST, detectável aqui.

export async function submitForApproval(reportId: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "enviado" })
    .eq("id", reportId)
    .select("id")
    .single();

  if (error) throw new Error("Não foi possível enviar o relatório: só o dono envia, e só um relatório em rascunho.");
}

// Tela /reembolso/aprovacoes: pela 052, só o master aprova ou rejeita
// (reimbursement_reports_approve com is_master()), nunca o próprio relatório e
// só a partir de 'enviado'.
export async function approveReport(reportId: string): Promise<void> {
  const supabase = createSupabaseClient();
  const approverId = await getCurrentUserId();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "aprovado", approved_by: approverId, approved_at: new Date().toISOString() })
    .eq("id", reportId)
    .select("id")
    .single();

  if (error) {
    throw new Error("Não foi possível aprovar: só o master aprova, nunca o próprio relatório, e só relatórios enviados.");
  }
}

export async function rejectReport(reportId: string, reason: string): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("reimbursement_reports")
    .update({ status: "rejeitado", rejection_reason: reason })
    .eq("id", reportId)
    .select("id")
    .single();

  if (error) {
    throw new Error("Não foi possível rejeitar: só o master rejeita, nunca o próprio relatório, e só relatórios enviados.");
  }
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
    .eq("id", reportId)
    .select("id")
    .single();

  if (error) throw new Error("Não foi possível reabrir: só o dono reabre, e só um relatório rejeitado.");
}
