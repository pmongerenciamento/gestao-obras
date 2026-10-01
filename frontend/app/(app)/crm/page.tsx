import Link from "next/link";
import { redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { KpiGrid } from "@/components/crm/KpiGrid";
import { SalesFunnel } from "@/components/crm/SalesFunnel";
import { RankingTable } from "@/components/crm/RankingTable";
import { getCrmDashboardData } from "@/lib/api/crm";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Dashboard do módulo CRM. RLS (024/025) já bloqueia leitura de quem não tem
// o módulo 'crm', mas confere aqui também pra redirecionar graciosamente em
// vez de renderizar uma tela vazia/quebrada pra quem não tem acesso.

export default async function CrmPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const userModules = await listUserModules();
  if (!userModules.includes("crm")) redirect("/");

  const { kpis, funnel, ranking } = await getCrmDashboardData();

  return (
    <div className="flex min-h-screen flex-col">
      <Header breadcrumb={[{ label: "Início", href: "/" }, { label: "CRM" }]} userEmail={user?.email} />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-8">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-black">CRM</h1>
          <Link href="/crm/pipeline" className="text-sm font-medium text-black/60 hover:text-black">
            Ver pipeline →
          </Link>
        </div>
        <KpiGrid kpis={kpis} />
        <SalesFunnel funnel={funnel} />
        <RankingTable ranking={ranking} />
      </main>
    </div>
  );
}
