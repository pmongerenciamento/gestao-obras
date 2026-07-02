export interface ProjectMember {
  id: string;
  name: string;
  avatarUrl?: string;
}

export type ProjectStatus = "em_andamento" | "pausado" | "concluido";

export interface ProjectSummary {
  id: string;
  name: string;
  clientName: string;
  city: string;
  imageUrl: string | null;
  lastSnapshotAt: string | null;
  status: ProjectStatus;
  members: ProjectMember[];
}

export interface ProjectDetail extends ProjectSummary {
  startDate: string | null;
  baselineFinish: string | null;
  forecastFinish: string | null;
}
