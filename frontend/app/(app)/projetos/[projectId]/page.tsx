import Link from "next/link";
import { notFound } from "next/navigation";
import {
  IconCalendarEvent,
  IconFlag3,
  IconCalendarStats,
  IconHistory,
} from "@tabler/icons-react";
import { getProject } from "@/lib/api/projects";
import { PROJECT_MODULES } from "@/lib/project-modules";

// Visão geral do projeto: datas principais + grid de módulos disponíveis

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

interface ProjectOverviewPageProps {
  params: Promise<{ projectId: string }>;
}

export default async function ProjectOverviewPage({ params }: ProjectOverviewPageProps) {
  const { projectId } = await params;
  const project = await getProject(projectId);

  if (!project) {
    notFound();
  }

  const dateCards = [
    { label: "Início do projeto", value: project.startDate, icon: IconCalendarEvent },
    { label: "Término linha de base", value: project.baselineFinish, icon: IconFlag3 },
    { label: "Término projetado", value: project.forecastFinish, icon: IconCalendarStats },
    { label: "Última importação", value: project.lastSnapshotAt, icon: IconHistory },
  ];

  return (
    <div className="flex flex-col gap-8">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {dateCards.map((card) => (
          <div key={card.label} className="rounded-lg border border-black/10 bg-white p-4">
            <p className="flex items-center gap-1.5 text-xs text-black/50">
              <card.icon size={16} className="shrink-0 text-black/40" />
              {card.label}
            </p>
            <p className="mt-1 text-lg font-semibold text-black">{formatDate(card.value)}</p>
          </div>
        ))}
      </div>
      <div>
        <h2 className="mb-4 text-sm font-semibold text-black/70">Módulos</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PROJECT_MODULES.map((module) => (
            <Link
              key={module.slug}
              href={`/projetos/${projectId}/${module.slug}`}
              className="flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-4 transition-colors hover:border-pmon-yellow hover:shadow-md"
            >
              <module.icon size={20} className="text-pmon-black/70" />
              <span className="font-medium text-black">{module.label}</span>
              <p className="text-xs text-black/50">{module.description}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
