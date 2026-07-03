import type {
  CreateStudyInput,
  SaveCyclesInput,
  SaveWbsOverridesInput,
  UpdateStudyInput,
} from "@/types/pre-planejamento";
import { apiFetch } from "@/lib/api/backend-client";
import { createClient } from "@/lib/supabase/client";

// Escrita client-side, mesmo padrão de lib/api/user-mutations.ts — quem chama
// recarrega via router.refresh() depois (o Server Component pai refaz o
// fetch de getStudy/listStudies e repassa props atualizadas pra baixo).

async function getAccessToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Sessão expirada.");
  return session.access_token;
}

export async function createStudy(projectId: string, input: CreateStudyInput): Promise<string> {
  const token = await getAccessToken();
  const raw = await apiFetch<{ id: string }>(`/api/v1/pre-planejamento/${projectId}/estudos`, token, {
    method: "POST",
    body: JSON.stringify({ name: input.name, start_date: input.startDate }),
  });
  return raw.id;
}

export async function updateStudy(
  projectId: string,
  estudoId: string,
  input: UpdateStudyInput,
): Promise<void> {
  const token = await getAccessToken();
  await apiFetch(`/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}`, token, {
    method: "PUT",
    body: JSON.stringify({
      name: input.name,
      start_date: input.startDate,
      holidays: input.holidays.map((h) => ({
        date: h.date,
        description: h.description,
        is_national: h.isNational,
      })),
    }),
  });
}

export async function deleteStudy(projectId: string, estudoId: string): Promise<void> {
  const token = await getAccessToken();
  await apiFetch(`/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}`, token, { method: "DELETE" });
}

export async function saveCycles(
  projectId: string,
  estudoId: string,
  input: SaveCyclesInput,
): Promise<void> {
  const token = await getAccessToken();
  await apiFetch(`/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}/ciclos`, token, {
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
}

export async function saveWbsOverrides(
  projectId: string,
  estudoId: string,
  input: SaveWbsOverridesInput,
): Promise<void> {
  const token = await getAccessToken();
  await apiFetch(`/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}/predecessores`, token, {
    method: "PUT",
    body: JSON.stringify({
      overrides: input.overrides.map((o) => ({
        cycle_id: o.cycleId,
        predecessor_ids: o.predecessorIds,
      })),
    }),
  });
}
