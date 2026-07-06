import type { Study, StudyDetail } from "@/types/pre-planejamento";
import { mapStudy, mapStudyDetail } from "@/lib/api/pre-planejamento-mappers";
import { createClient } from "@/lib/supabase/server";

// Leitura server-side direto no Supabase (RLS de sim_studies e afins cobre
// "é dono do projeto?", mesmo padrão de lib/api/projects.ts) — não depende
// mais do backend FastAPI. Escrita fica em lib/api/pre-planejamento-mutations.ts;
// createStudy/updateStudy/deleteStudy também já foram migradas pra Supabase
// direto lá, só saveCycles/saveWbsOverrides continuam via apiFetch.

export async function listStudies(projectId: string): Promise<Study[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("sim_studies")
    .select("id, project_id, name, start_date, duration_months, created_at")
    .eq("project_id", projectId)
    .order("created_at", { ascending: false });

  if (error || !data) return [];
  return data.map(mapStudy);
}

export async function getStudy(projectId: string, estudoId: string): Promise<StudyDetail | null> {
  const supabase = await createClient();

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
