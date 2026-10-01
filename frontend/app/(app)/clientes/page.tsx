import { Header } from "@/components/layout/Header";
import { ClientsView } from "@/components/clients/ClientsView";
import { listClients } from "@/lib/api/clients";
import { createClient } from "@/lib/supabase/server";

export default async function ClientsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const clients = await listClients();

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[{ label: "Projetos", href: "/projetos" }, { label: "Clientes" }]}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <ClientsView clients={clients} />
      </main>
    </div>
  );
}
