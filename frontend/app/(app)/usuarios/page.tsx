import { redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { UserTable } from "@/components/users/UserTable";
import { listProjects } from "@/lib/api/projects";
import { listUsers } from "@/lib/api/users";
import { isMasterUser } from "@/lib/auth/roles";
import { createClient } from "@/lib/supabase/server";

// Tela de gestão de usuários — só o usuário master enxerga (link real em
// components/layout/AdminBar.tsx). A checagem que importa de verdade é a do
// backend (app/core/roles.py::require_master); esta aqui só evita que um
// usuário comum veja a tela.

export default async function UsersPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!isMasterUser(user?.email)) redirect("/");

  const [users, projects] = await Promise.all([listUsers(), listProjects()]);
  const projectOptions = projects.map((project) => ({ id: project.id, name: project.name }));

  return (
    <div className="flex min-h-screen flex-col">
      <Header breadcrumb={[{ label: "Projetos", href: "/" }, { label: "Usuários" }]} userEmail={user?.email} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <UserTable users={users} projects={projectOptions} />
      </main>
    </div>
  );
}
