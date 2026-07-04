// Espelha backend/app/schemas/pre_planejamento.py

export interface Study {
  id: string;
  projectId: string;
  name: string;
  startDate: string;
  durationMonths: number | null;
  createdAt: string;
}

export interface Service {
  id: string;
  name: string;
  color: string;
  orderIndex: number;
  lagDays: number;
}

export interface Floor {
  id: string;
  groupName: string;
  floorName: string;
  orderIndex: number;
}

export interface Cycle {
  id: string;
  serviceId: string;
  floorId: string;
  durationDays: number;
}

export interface Holiday {
  id: string;
  date: string;
  description: string;
  isNational: boolean;
}

export interface Predecessor {
  cycleId: string;
  predecessorId: string;
}

export interface StudyDetail extends Study {
  services: Service[];
  floors: Floor[];
  cycles: Cycle[];
  holidays: Holiday[];
  predecessors: Predecessor[];
}

export interface CreateStudyInput {
  name: string;
  startDate: string;
  durationMonths: number;
}

export interface HolidayInput {
  date: string;
  description: string;
  isNational: boolean;
}

export interface UpdateStudyInput {
  name: string;
  startDate: string;
  holidays: HolidayInput[];
}

export interface ServiceInput {
  id?: string;
  name: string;
  color: string;
  orderIndex: number;
  lagDays: number;
}

export interface FloorInput {
  id?: string;
  groupName: string;
  floorName: string;
  orderIndex: number;
}

export interface CycleInput {
  serviceIndex: number;
  floorIndex: number;
  durationDays: number;
}

export interface SaveCyclesInput {
  services: ServiceInput[];
  floors: FloorInput[];
  cycles: CycleInput[];
}

export interface WbsOverrideInput {
  cycleId: string;
  predecessorIds: string[];
}

export interface SaveWbsOverridesInput {
  overrides: WbsOverrideInput[];
}
