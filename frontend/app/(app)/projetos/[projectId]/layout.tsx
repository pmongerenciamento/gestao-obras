import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { ProjectSidebar } from "@/components/layout/ProjectSidebar";
import { getProject } from "@/lib/api/projects";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Layout da página do projeto: topbar com breadcrumb + sidebar de navegação entre os módulos

interface ProjectLayoutProps {
  children: ReactNode;
  params: Promise<{ projectId: string }>;
}

export default async function ProjectLayout({ children, params }: ProjectLayoutProps) {
  const { projectId } = await params;
  const project = await getProject(projectId);

  if (!project) {
    notFound();
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const userModules = await listUserModules();
  const hasCrmAccess = userModules.includes("crm");

  return (
    <>
      <Header
        breadcrumb={[{ label: "Projetos", href: "/projetos" }, { label: project.name }]}
        userEmail={user?.email}
      />
      <div className="flex">
        <ProjectSidebar project={project} projectId={projectId} hasCrmAccess={hasCrmAccess} />
        <main className="min-w-0 flex-1 px-6 py-8">{children}</main>
      </div>
    </>
  );
}
