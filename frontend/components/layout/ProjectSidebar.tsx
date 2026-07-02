"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconHome } from "@tabler/icons-react";
import type { ProjectDetail } from "@/types/project";
import { PROJECT_MODULES } from "@/lib/project-modules";

// Sidebar da tela interna do projeto: dados do empreendimento + nav dos módulos.
// Substitui o antigo stub ProjectTabs.tsx — o mockup usa sidebar, não abas.

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

interface ProjectSidebarProps {
  project: ProjectDetail;
  projectId: string;
}

export function ProjectSidebar({ project, projectId }: ProjectSidebarProps) {
  const pathname = usePathname();
  const overviewHref = `/projetos/${projectId}`;

  const navItems = [
    { href: overviewHref, label: "Visão geral", icon: IconHome },
    ...PROJECT_MODULES.map((m) => ({
      href: `${overviewHref}/${m.slug}`,
      label: m.label,
      icon: m.icon,
    })),
  ];

  return (
    <aside className="flex w-[220px] shrink-0 flex-col border-r border-black/10 bg-white">
      <div className="border-b border-black/10 p-4">
        <div className="relative mb-3 h-24 w-full overflow-hidden rounded-md bg-black/5">
          {project.imageUrl ? (
            <Image src={project.imageUrl} alt={project.name} fill className="object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-black/30">
              Sem imagem
            </div>
          )}
        </div>
        <p className="text-xs text-black/50">{project.clientName}</p>
        <h2 className="text-sm font-semibold text-black">{project.name}</h2>
        <p className="text-xs text-black/60">{project.city}</p>
        <span className="mt-2 inline-block rounded-full border border-pmon-yellow/40 bg-pmon-yellow/10 px-2 py-0.5 text-[11px] text-pmon-black/70">
          Último snapshot: {formatDate(project.lastSnapshotAt)}
        </span>
      </div>
      <nav className="flex flex-col gap-0.5 p-2">
        {navItems.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2 border-l-4 py-2 pl-2 pr-3 text-sm ${
                active
                  ? "border-pmon-yellow bg-pmon-yellow/10 font-medium text-pmon-black"
                  : "border-transparent text-black/70 hover:bg-black/5"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
