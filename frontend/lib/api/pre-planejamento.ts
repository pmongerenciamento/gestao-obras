import type { Cycle, Floor, Holiday, Service, Study, StudyDetail } from "@/types/pre-planejamento";
import { apiFetch } from "@/lib/api/backend-client";
import { createClient } from "@/lib/supabase/server";

// Leitura server-side (sessão via cookie), mesmo padrão de lib/api/users.ts.
// Escrita fica em lib/api/pre-planejamento-mutations.ts (client-side), mesma
// separação de user-mutations.ts.

interface RawStudy {
  id: string;
  project_id: string;
  name: string;
  start_date: string;
  created_at: string;
}

interface RawService {
  id: string;
  name: string;
  color: string;
  order_index: number;
  lag_days: number;
}

interface RawFloor {
  id: string;
  group_name: string;
  floor_name: string;
  order_index: number;
}

interface RawCycle {
  id: string;
  service_id: string;
  floor_id: string;
  duration_days: number;
}

interface RawHoliday {
  id: string;
  date: string;
  description: string;
  is_national: boolean;
}

interface RawStudyDetail extends RawStudy {
  services: RawService[];
  floors: RawFloor[];
  cycles: RawCycle[];
  holidays: RawHoliday[];
}

function mapStudy(raw: RawStudy): Study {
  return {
    id: raw.id,
    projectId: raw.project_id,
    name: raw.name,
    startDate: raw.start_date,
    createdAt: raw.created_at,
  };
}

function mapService(raw: RawService): Service {
  return { id: raw.id, name: raw.name, color: raw.color, orderIndex: raw.order_index, lagDays: raw.lag_days };
}

function mapFloor(raw: RawFloor): Floor {
  return { id: raw.id, groupName: raw.group_name, floorName: raw.floor_name, orderIndex: raw.order_index };
}

function mapCycle(raw: RawCycle): Cycle {
  return { id: raw.id, serviceId: raw.service_id, floorId: raw.floor_id, durationDays: raw.duration_days };
}

function mapHoliday(raw: RawHoliday): Holiday {
  return { id: raw.id, date: raw.date, description: raw.description, isNational: raw.is_national };
}

async function getAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

export async function listStudies(projectId: string): Promise<Study[]> {
  const token = await getAccessToken();
  if (!token) return [];
  const raw = await apiFetch<RawStudy[]>(`/api/v1/pre-planejamento/${projectId}/estudos`, token);
  return raw.map(mapStudy);
}

export async function getStudy(projectId: string, estudoId: string): Promise<StudyDetail | null> {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    const raw = await apiFetch<RawStudyDetail>(
      `/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}`,
      token,
    );
    return {
      ...mapStudy(raw),
      services: raw.services.map(mapService),
      floors: raw.floors.map(mapFloor),
      cycles: raw.cycles.map(mapCycle),
      holidays: raw.holidays.map(mapHoliday),
    };
  } catch {
    return null;
  }
}
