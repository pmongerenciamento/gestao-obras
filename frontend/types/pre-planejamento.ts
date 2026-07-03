// Espelha backend/app/schemas/pre_planejamento.py

export interface Study {
  id: string;
  projectId: string;
  name: string;
  startDate: string;
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

export interface StudyDetail extends Study {
  services: Service[];
  floors: Floor[];
  cycles: Cycle[];
  holidays: Holiday[];
}

export interface CreateStudyInput {
  name: string;
  startDate: string;
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
  name: string;
  color: string;
  orderIndex: number;
  lagDays: number;
}

export interface FloorInput {
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
