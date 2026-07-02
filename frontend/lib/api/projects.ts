import type { ProjectDetail, ProjectSummary } from "@/types/project";

// TODO: substituir por fetch real em GET /api/v1/projects quando o endpoint existir
// (backend/app/api/v1/routes_projects.py ainda é um stub). Mantendo a assinatura async
// pra troca ser isolada a este arquivo.

const MOCK_PROJECTS: ProjectDetail[] = [
  {
    id: "1",
    name: "Residencial Vista Verde",
    clientName: "Construtora Alfa",
    city: "Curitiba, PR",
    imageUrl: null,
    lastSnapshotAt: "2026-06-28T14:00:00Z",
    status: "em_andamento",
    members: [
      { id: "u1", name: "Diego Ferreira" },
      { id: "u2", name: "Marina Souza" },
    ],
    startDate: "2025-02-01",
    baselineFinish: "2026-12-15",
    forecastFinish: "2027-01-20",
  },
  {
    id: "2",
    name: "Edifício Horizonte",
    clientName: "Construtora Beta",
    city: "São José dos Pinhais, PR",
    imageUrl: null,
    lastSnapshotAt: "2026-05-30T09:30:00Z",
    status: "pausado",
    members: [{ id: "u3", name: "Carlos Lima" }],
    startDate: "2024-08-10",
    baselineFinish: "2026-10-01",
    forecastFinish: "2027-03-01",
  },
  {
    id: "3",
    name: "Condomínio Parque das Águas",
    clientName: "Construtora Gama",
    city: "Pinhais, PR",
    imageUrl: null,
    lastSnapshotAt: "2026-07-01T18:15:00Z",
    status: "em_andamento",
    members: [
      { id: "u1", name: "Diego Ferreira" },
      { id: "u4", name: "Paula Nogueira" },
      { id: "u5", name: "Rafael Costa" },
    ],
    startDate: "2025-11-01",
    baselineFinish: "2027-06-30",
    forecastFinish: "2027-06-30",
  },
  {
    id: "4",
    name: "Torre Empresarial Centro",
    clientName: "Construtora Alfa",
    city: "Curitiba, PR",
    imageUrl: null,
    lastSnapshotAt: "2026-01-15T11:00:00Z",
    status: "concluido",
    members: [{ id: "u2", name: "Marina Souza" }],
    startDate: "2023-03-01",
    baselineFinish: "2025-12-20",
    forecastFinish: "2026-01-10",
  },
];

export async function listProjects(): Promise<ProjectSummary[]> {
  return MOCK_PROJECTS;
}

export async function getProject(id: string): Promise<ProjectDetail | null> {
  return MOCK_PROJECTS.find((project) => project.id === id) ?? null;
}
