import Image from "next/image";
import Link from "next/link";
import { IconMapPin } from "@tabler/icons-react";
import type { ProjectSummary } from "@/types/project";

// Card de projeto no painel principal: imagem, cliente, nome, cidade, último snapshot, membros, status

const STATUS_LABEL: Record<ProjectSummary["status"], string> = {
  em_andamento: "Em andamento",
  pausado: "Pausado",
  concluido: "Concluído",
};

const STATUS_STYLE: Record<ProjectSummary["status"], string> = {
  em_andamento: "bg-green-100 text-green-800",
  pausado: "bg-yellow-100 text-yellow-800",
  concluido: "bg-black/10 text-black/60",
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

export function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <Link
      href={`/projetos/${project.id}`}
      className="block overflow-hidden rounded-lg border border-black/10 bg-white shadow-sm transition-colors transition-shadow hover:border-pmon-yellow hover:shadow-md"
    >
      <div className="relative h-36 w-full bg-black/5">
        {project.imageUrl ? (
          <Image src={project.imageUrl} alt={project.name} fill className="object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-black/30">
            Sem imagem
          </div>
        )}
        <span
          className={`absolute right-2 top-2 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[project.status]}`}
        >
          {STATUS_LABEL[project.status]}
        </span>
      </div>
      <div className="flex flex-col gap-1 p-4">
        <p className="text-xs text-black/50">{project.clientName}</p>
        <h3 className="font-semibold text-black">{project.name}</h3>
        <p className="flex items-center gap-1 text-sm text-black/60">
          <IconMapPin size={14} className="shrink-0 text-black/40" />
          {project.city}
        </p>
        <p className="text-xs text-black/40">
          Último snapshot: {formatDate(project.lastSnapshotAt)}
        </p>
        <div className="mt-2 flex -space-x-2">
          {project.members.map((member) => (
            <div
              key={member.id}
              title={member.name}
              className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-white bg-pmon-yellow text-[10px] font-semibold text-pmon-black"
            >
              {member.name.charAt(0).toUpperCase()}
            </div>
          ))}
        </div>
      </div>
    </Link>
  );
}
