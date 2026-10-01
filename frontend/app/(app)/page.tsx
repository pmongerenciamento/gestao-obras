import { Header } from "@/components/layout/Header";
import { Greeting } from "@/components/home/Greeting";
import { ModuleGrid } from "@/components/home/ModuleGrid";
import { UpdatesFeed } from "@/components/home/UpdatesFeed";
import { PmonSpace } from "@/components/home/PmonSpace";
import { listUserModules } from "@/lib/api/modules";
import { getProfileFullName } from "@/lib/api/profile";
import { createClient } from "@/lib/supabase/server";

// Tela inicial: saudação + grid de módulos (filtrado por
// profile_modules do usuário logado) + mural + espaço PMON.
export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [userModules, fullName] = await Promise.all([
    listUserModules(),
    user ? getProfileFullName(user.id) : Promise.resolve(null),
  ]);

  const displayName = fullName ?? user?.email ?? "";

  return (
    <div className="flex min-h-screen flex-col">
      <Header breadcrumb={[{ label: "Início" }]} userEmail={user?.email} />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-8">
        <Greeting name={displayName} />
        <ModuleGrid userModules={userModules} />
        <div className="grid gap-4 lg:grid-cols-2">
          <UpdatesFeed />
          <PmonSpace />
        </div>
      </main>
    </div>
  );
}
