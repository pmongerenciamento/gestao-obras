import { Header } from "@/components/layout/Header";
import { ProjectCard } from "@/components/layout/ProjectCard";
import { AdminBar } from "@/components/layout/AdminBar";
import { Button } from "@/components/ui/Button";
import { listProjects } from "@/lib/api/projects";
import { isMasterUser } from "@/lib/auth/roles";
import { createClient } from "@/lib/supabase/server";

// Painel principal: cards de projetos do usuário logado + botão "Novo projeto"

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const projects = await listProjects();
  const activeCount = projects.filter((project) => project.status === "em_andamento").length;

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[{ label: "Projetos" }]}
        subtitle={`${activeCount} projetos ativos`}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-black">Projetos</h1>
          <Button className="cursor-not-allowed">Novo projeto</Button>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
        {isMasterUser(user?.email) && <AdminBar />}
      </main>
    </div>
  );
}
