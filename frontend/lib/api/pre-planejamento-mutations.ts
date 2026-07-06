import type { SupabaseClient } from "@supabase/supabase-js";
import type {
  CreateStudyInput,
  CycleInput,
  FloorInput,
  SaveCyclesInput,
  SaveWbsOverridesInput,
  ServiceInput,
  StudyDetail,
  UpdateStudyInput,
} from "@/types/pre-planejamento";
import { fetchStudyDetail } from "@/lib/api/pre-planejamento-queries";
import { generateNationalHolidays } from "@/lib/pre-planejamento/holidays";
import { createClient } from "@/lib/supabase/client";

// Escrita client-side, mesmo padrão de lib/api/user-mutations.ts — quem chama
// recarrega via router.refresh() depois (o Server Component pai refaz o
// fetch de getStudy/listStudies e repassa props atualizadas pra baixo).
// Tudo aqui vai direto no Supabase (RLS de sim_studies e afins cobre "é dono
// do projeto?", mesmo padrão de lib/api/projects.ts) — não depende mais do
// backend FastAPI.
//
// saveCycles/saveWbsOverrides reimplementam client-side o upsert
// reconciliador que antes rodava numa única transação Postgres (ver
// backend/app/domain/pre_planejamento/repository.py): update o que já
// existe, insere o que é novo, apaga o que sumiu do payload. Sem transação
// cross-request — se uma chamada no meio da sequência falhar, o estudo pode
// ficar com um subconjunto salvo (ex.: services/floors atualizados mas
// cycles não); o catch de cada componente chamador já mostra erro e o
// usuário tenta salvar de novo.

async function upsertReconciled<T extends { id?: string }>(
  supabase: SupabaseClient,
  table: string,
  studyId: string,
  items: T[],
  toRow: (item: T) => Record<string, unknown>,
): Promise<string[]> {
  const ids = new Array<string>(items.length);
  const existingIdx: number[] = [];
  const freshIdx: number[] = [];
  items.forEach((item, i) => (item.id ? existingIdx.push(i) : freshIdx.push(i)));

  if (existingIdx.length > 0) {
    const { error } = await supabase.from(table).upsert(
      existingIdx.map((i) => ({ id: items[i].id, study_id: studyId, ...toRow(items[i]) })),
      { onConflict: "id" },
    );
    if (error) throw error;
    existingIdx.forEach((i) => {
      ids[i] = items[i].id!;
    });
  }

  if (freshIdx.length > 0) {
    const { data, error } = await supabase
      .from(table)
      .insert(freshIdx.map((i) => ({ study_id: studyId, ...toRow(items[i]) })))
      .select("id");
    if (error || !data) throw error ?? new Error(`Falha ao salvar ${table}.`);
    freshIdx.forEach((i, n) => {
      ids[i] = data[n].id;
    });
  }

  await deleteMissing(supabase, table, studyId, ids);
  return ids;
}

async function deleteMissing(
  supabase: SupabaseClient,
  table: string,
  studyId: string,
  keepIds: string[],
): Promise<void> {
  let query = supabase.from(table).delete().eq("study_id", studyId);
  if (keepIds.length > 0) {
    query = query.not("id", "in", `(${keepIds.join(",")})`);
  }
  const { error } = await query;
  if (error) throw error;
}

function upsertServices(supabase: SupabaseClient, studyId: string, services: ServiceInput[]): Promise<string[]> {
  return upsertReconciled(supabase, "sim_services", studyId, services, (s) => ({
    name: s.name,
    color: s.color,
    order_index: s.orderIndex,
    lag_days: s.lagDays,
  }));
}

function upsertFloors(supabase: SupabaseClient, studyId: string, floors: FloorInput[]): Promise<string[]> {
  return upsertReconciled(supabase, "sim_floors", studyId, floors, (f) => ({
    group_name: f.groupName,
    floor_name: f.floorName,
    order_index: f.orderIndex,
  }));
}

async function upsertCycles(
  supabase: SupabaseClient,
  studyId: string,
  serviceIds: string[],
  floorIds: string[],
  cycles: CycleInput[],
): Promise<void> {
  if (cycles.length === 0) {
    await deleteMissing(supabase, "sim_cycles", studyId, []);
    return;
  }

  const { data, error } = await supabase
    .from("sim_cycles")
    .upsert(
      cycles.map((c) => ({
        study_id: studyId,
        service_id: serviceIds[c.serviceIndex],
        floor_id: floorIds[c.floorIndex],
        duration_days: c.durationDays,
      })),
      { onConflict: "service_id,floor_id" },
    )
    .select("id");
  if (error || !data) throw error ?? new Error("Falha ao salvar ciclos.");

  // Cascade de sim_cycles pra sim_wbs_overrides cuida de limpar predecessores
  // que apontavam pra um ciclo removido aqui (célula que o usuário apagou).
  await deleteMissing(supabase, "sim_cycles", studyId, data.map((row) => row.id));
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

// Devolvem o StudyDetail atualizado (mesma leitura de lib/api/pre-planejamento.ts,
// via lib/api/pre-planejamento-queries.ts) — permite encadear outra ação (ex.:
// "Replicar torre" resolve os ids dos ciclos novos e já manda os predecessores
// remapeados) sem esperar um próximo GET/router.refresh().

export async function saveCycles(
  projectId: string,
  estudoId: string,
  input: SaveCyclesInput,
): Promise<StudyDetail> {
  const supabase = createClient();

  const serviceIds = await upsertServices(supabase, estudoId, input.services);
  const floorIds = await upsertFloors(supabase, estudoId, input.floors);
  await upsertCycles(supabase, estudoId, serviceIds, floorIds, input.cycles);

  const study = await fetchStudyDetail(supabase, projectId, estudoId);
  if (!study) throw new Error("Cenário não encontrado.");
  return study;
}

export async function saveWbsOverrides(
  projectId: string,
  estudoId: string,
  input: SaveWbsOverridesInput,
): Promise<StudyDetail> {
  const supabase = createClient();

  const { error: deleteError } = await supabase.from("sim_wbs_overrides").delete().eq("study_id", estudoId);
  if (deleteError) throw deleteError;

  const rows = input.overrides.flatMap((o) =>
    o.predecessorIds.map((predecessorId) => ({
      study_id: estudoId,
      cycle_id: o.cycleId,
      predecessor_id: predecessorId,
    })),
  );
  if (rows.length > 0) {
    const { error: insertError } = await supabase
      .from("sim_wbs_overrides")
      .upsert(rows, { onConflict: "cycle_id,predecessor_id", ignoreDuplicates: true });
    if (insertError) throw insertError;
  }

  const study = await fetchStudyDetail(supabase, projectId, estudoId);
  if (!study) throw new Error("Cenário não encontrado.");
  return study;
}
