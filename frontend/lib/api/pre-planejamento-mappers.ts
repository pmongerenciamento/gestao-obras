import type { Cycle, Floor, Holiday, Predecessor, Service, Study, StudyDetail } from "@/types/pre-planejamento";

// Mapeamento snake_case (backend) -> camelCase (frontend), puro e sem
// dependência de server/client do Supabase — reusado tanto por
// lib/api/pre-planejamento.ts (leitura server-side) quanto por
// pre-planejamento-mutations.ts (escrita client-side, que também precisa do
// StudyDetail atualizado devolvido pelo PUT pra recalcular sem esperar um
// novo GET, ex.: "Replicar torre").

export interface RawStudy {
  id: string;
  project_id: string;
  name: string;
  start_date: string;
  duration_months: number | null;
  created_at: string;
}

export interface RawService {
  id: string;
  name: string;
  color: string;
  order_index: number;
  lag_days: number;
}

export interface RawFloor {
  id: string;
  group_name: string;
  floor_name: string;
  order_index: number;
}

export interface RawCycle {
  id: string;
  service_id: string;
  floor_id: string;
  duration_days: number;
}

export interface RawHoliday {
  id: string;
  date: string;
  description: string;
  is_national: boolean;
}

export interface RawPredecessor {
  cycle_id: string;
  predecessor_id: string;
}

export interface RawStudyDetail extends RawStudy {
  services: RawService[];
  floors: RawFloor[];
  cycles: RawCycle[];
  holidays: RawHoliday[];
  predecessors: RawPredecessor[];
}

export function mapStudy(raw: RawStudy): Study {
  return {
    id: raw.id,
    projectId: raw.project_id,
    name: raw.name,
    startDate: raw.start_date,
    durationMonths: raw.duration_months,
    createdAt: raw.created_at,
  };
}

export function mapService(raw: RawService): Service {
  return { id: raw.id, name: raw.name, color: raw.color, orderIndex: raw.order_index, lagDays: raw.lag_days };
}

export function mapFloor(raw: RawFloor): Floor {
  return { id: raw.id, groupName: raw.group_name, floorName: raw.floor_name, orderIndex: raw.order_index };
}

export function mapCycle(raw: RawCycle): Cycle {
  return { id: raw.id, serviceId: raw.service_id, floorId: raw.floor_id, durationDays: raw.duration_days };
}

export function mapHoliday(raw: RawHoliday): Holiday {
  return { id: raw.id, date: raw.date, description: raw.description, isNational: raw.is_national };
}

export function mapPredecessor(raw: RawPredecessor): Predecessor {
  return { cycleId: raw.cycle_id, predecessorId: raw.predecessor_id };
}

export function mapStudyDetail(raw: RawStudyDetail): StudyDetail {
  return {
    ...mapStudy(raw),
    services: raw.services.map(mapService),
    floors: raw.floors.map(mapFloor),
    cycles: raw.cycles.map(mapCycle),
    holidays: raw.holidays.map(mapHoliday),
    predecessors: raw.predecessors.map(mapPredecessor),
  };
}
