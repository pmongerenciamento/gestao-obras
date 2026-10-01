import { redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { PipelineView } from "@/components/crm/PipelineView";
import { getPipelineBoard } from "@/lib/api/pipeline";
import { getNextClientCode, listClients } from "@/lib/api/clients";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Board de pipeline de vendas (Kanban por pipeline_stage). RLS (024/025/026)
// já bloqueia leitura de quem não tem o módulo 'crm', mas confere aqui também
// pra redirecionar graciosamente em vez de renderizar uma tela vazia/quebrada.

export default async function PipelinePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const userModules = await listUserModules();
  if (!userModules.includes("crm")) redirect("/");

  const [columns, clients, suggestedClientCode] = await Promise.all([
    getPipelineBoard(),
    listClients(),
    getNextClientCode(),
  ]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[{ label: "Início", href: "/" }, { label: "CRM", href: "/crm" }, { label: "Pipeline" }]}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-6 py-8">
        <PipelineView columns={columns} clients={clients} suggestedClientCode={suggestedClientCode} />
      </main>
    </div>
  );
}
