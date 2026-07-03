"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { IconMapPin, IconDots } from "@tabler/icons-react";
import type { ProjectSummary } from "@/types/project";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { deleteProject } from "@/lib/api/project-mutations";

// Card de projeto no painel principal: imagem, cliente, nome, cidade, último snapshot,
// membros, status. Menu de três pontos (só usuário master) permite excluir o projeto.

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

interface ProjectCardProps {
  project: ProjectSummary;
  isMaster: boolean;
}

export function ProjectCard({ project, isMaster }: ProjectCardProps) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleConfirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteProject(project.id);
      router.refresh();
      setConfirmOpen(false);
    } catch {
      setDeleteError("Não foi possível excluir o projeto. Tente novamente.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="group relative overflow-hidden rounded-lg border border-black/10 bg-white shadow-sm transition-colors transition-shadow hover:border-pmon-yellow hover:shadow-md">
      <Link href={`/projetos/${project.id}`} className="absolute inset-0 z-10" />

      <div className="relative h-[160px] w-full bg-black/5">
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

        {isMaster && (
          <div
            className="absolute left-2 top-2 z-20"
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget)) setMenuOpen(false);
            }}
          >
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setMenuOpen((open) => !open);
              }}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-white/90 text-black/70 shadow-sm hover:bg-white"
            >
              <IconDots size={16} />
            </button>
            {menuOpen && (
              <div className="absolute left-0 top-full z-20 mt-1 w-40 rounded-md border border-black/10 bg-white py-1 shadow-lg">
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setMenuOpen(false);
                    setConfirmOpen(true);
                  }}
                  className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                >
                  Excluir projeto
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="relative flex flex-col gap-1 p-4">
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

      <ConfirmDialog
        open={confirmOpen}
        title="Excluir projeto"
        description={`Tem certeza que deseja excluir o projeto ${project.name}? Esta ação não pode ser desfeita.`}
        confirmLabel="Excluir"
        loadingLabel="Excluindo..."
        isLoading={deleting}
        error={deleteError}
        onConfirm={handleConfirmDelete}
        onCancel={() => {
          setConfirmOpen(false);
          setDeleteError(null);
        }}
      />
    </div>
  );
}
