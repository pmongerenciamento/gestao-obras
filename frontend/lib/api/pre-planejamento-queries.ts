import type { SupabaseClient } from "@supabase/supabase-js";
import type { Study, StudyDetail } from "@/types/pre-planejamento";
import { mapStudy, mapStudyDetail } from "@/lib/api/pre-planejamento-mappers";

// Leitura de sim_studies e tabelas relacionadas, compartilhada entre
// lib/api/pre-planejamento.ts (Server Component, cliente via
// lib/supabase/server) e lib/api/pre-planejamento-mutations.ts (Client
// Component, cliente via lib/supabase/client) — saveCycles/saveWbsOverrides
// devolvem o StudyDetail atualizado sem esperar um próximo
// GET/router.refresh(), mesma necessidade que a leitura server-side.

export async function fetchStudies(supabase: SupabaseClient, projectId: string): Promise<Study[]> {
  const { data, error } = await supabase
    .from("sim_studies")
    .select("id, project_id, name, start_date, duration_months, created_at")
    .eq("project_id", projectId)
    .order("created_at", { ascending: false });

  if (error || !data) return [];
  return data.map(mapStudy);
}

export async function fetchStudyDetail(
  supabase: SupabaseClient,
  projectId: string,
  estudoId: string,
): Promise<StudyDetail | null> {
  const { data: study, error: studyError } = await supabase
    .from("sim_studies")
    .select("id, project_id, name, start_date, duration_months, created_at")
    .eq("id", estudoId)
    .eq("project_id", projectId)
    .maybeSingle();
  if (studyError || !study) return null;

  const [services, floors, cycles, holidays, predecessors] = await Promise.all([
    supabase
      .from("sim_services")
      .select("id, name, color, order_index, lag_days")
      .eq("study_id", estudoId)
      .order("order_index"),
    supabase
      .from("sim_floors")
      .select("id, group_name, floor_name, order_index")
      .eq("study_id", estudoId)
      .order("order_index"),
    supabase.from("sim_cycles").select("id, service_id, floor_id, duration_days").eq("study_id", estudoId),
    supabase
      .from("sim_holidays")
      .select("id, date, description, is_national")
      .eq("study_id", estudoId)
      .order("date"),
    supabase.from("sim_wbs_overrides").select("cycle_id, predecessor_id").eq("study_id", estudoId),
  ]);

  if (services.error || floors.error || cycles.error || holidays.error || predecessors.error) return null;

  return mapStudyDetail({
    ...study,
    services: services.data ?? [],
    floors: floors.data ?? [],
    cycles: cycles.data ?? [],
    holidays: holidays.data ?? [],
    predecessors: predecessors.data ?? [],
  });
}
