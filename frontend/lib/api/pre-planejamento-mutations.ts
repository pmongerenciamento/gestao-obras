import type {
  CreateStudyInput,
  SaveCyclesInput,
  SaveWbsOverridesInput,
  StudyDetail,
  UpdateStudyInput,
} from "@/types/pre-planejamento";
import { apiFetch } from "@/lib/api/backend-client";
import { mapStudyDetail, type RawStudyDetail } from "@/lib/api/pre-planejamento-mappers";
import { generateNationalHolidays } from "@/lib/pre-planejamento/holidays";
import { createClient } from "@/lib/supabase/client";

// Escrita client-side, mesmo padrão de lib/api/user-mutations.ts — quem chama
// recarrega via router.refresh() depois (o Server Component pai refaz o
// fetch de getStudy/listStudies e repassa props atualizadas pra baixo).
//
// createStudy/updateStudy/deleteStudy vão direto no Supabase (RLS de
// sim_studies/sim_holidays já cobre "é dono do projeto?", mesmo padrão de
// lib/api/projects.ts) — não dependem do backend FastAPI. saveCycles e
// saveWbsOverrides continuam via apiFetch: fazem upsert reconciliador
// multi-tabela numa única transação Postgres (ver
// backend/app/domain/pre_planejamento/repository.py), que o cliente Supabase
// não reproduz com segurança em várias chamadas sequenciais sem transação.

async function getAccessToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Sessão expirada.");
  return session.access_token;
}

export async function createStudy(projectId: string, input: CreateStudyInput): Promise<string> {
  const supabase = createClient();

  const { data, error } = await supabase
    .from("sim_studies")
    .insert({
      project_id: projectId,
      name: input.name,
      start_date: input.startDate,
      duration_months: input.durationMonths,
    })
    .select("id")
    .single();
  if (error || !data) throw error ?? new Error("Falha ao criar o cenário.");

  const startYear = Number(input.startDate.slice(0, 4));
  const holidays = generateNationalHolidays(startYear);
  const { error: holidaysError } = await supabase.from("sim_holidays").upsert(
    holidays.map((h) => ({ study_id: data.id, date: h.date, description: h.description, is_national: true })),
    { onConflict: "study_id,date", ignoreDuplicates: true },
  );
  if (holidaysError) throw holidaysError;

  return data.id;
}

export async function updateStudy(
  projectId: string,
  estudoId: string,
  input: UpdateStudyInput,
): Promise<void> {
  const supabase = createClient();

  const { error: updateError } = await supabase
    .from("sim_studies")
    .update({ name: input.name, start_date: input.startDate })
    .eq("id", estudoId)
    .eq("project_id", projectId);
  if (updateError) throw updateError;

  const { error: deleteError } = await supabase.from("sim_holidays").delete().eq("study_id", estudoId);
  if (deleteError) throw deleteError;

  if (input.holidays.length > 0) {
    const { error: insertError } = await supabase.from("sim_holidays").insert(
      input.holidays.map((h) => ({
        study_id: estudoId,
        date: h.date,
        description: h.description,
        is_national: h.isNational,
      })),
    );
    if (insertError) throw insertError;
  }
}

export async function deleteStudy(projectId: string, estudoId: string): Promise<void> {
  const supabase = createClient();
  const { error } = await supabase.from("sim_studies").delete().eq("id", estudoId).eq("project_id", projectId);
  if (error) throw error;
}

// Devolvem o StudyDetail atualizado (o PUT do backend já devolve isso) —
// permite encadear outra ação (ex.: "Replicar torre" resolve os ids dos
// ciclos novos e já manda os predecessores remapeados) sem esperar um
// próximo GET/router.refresh().

export async function saveCycles(
  projectId: string,
  estudoId: string,
  input: SaveCyclesInput,
): Promise<StudyDetail> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  const raw = await apiFetch<RawStudyDetail>(`/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}/ciclos`, token, {
    method: "PUT",
    body: JSON.stringify({
      services: input.services.map((s) => ({
        id: s.id,
        name: s.name,
        color: s.color,
        order_index: s.orderIndex,
        lag_days: s.lagDays,
      })),
      floors: input.floors.map((f) => ({
        id: f.id,
        group_name: f.groupName,
        floor_name: f.floorName,
        order_index: f.orderIndex,
      })),
      cycles: input.cycles.map((c) => ({
        service_index: c.serviceIndex,
        floor_index: c.floorIndex,
        duration_days: c.durationDays,
      })),
    }),
  });
  return mapStudyDetail(raw);
}

export async function saveWbsOverrides(
  projectId: string,
  estudoId: string,
  input: SaveWbsOverridesInput,
): Promise<StudyDetail> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  const raw = await apiFetch<RawStudyDetail>(
    `/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}/predecessores`,
    token,
    {
      method: "PUT",
      body: JSON.stringify({
        overrides: input.overrides.map((o) => ({
          cycle_id: o.cycleId,
          predecessor_ids: o.predecessorIds,
        })),
      }),
    },
  );
  return mapStudyDetail(raw);
}
