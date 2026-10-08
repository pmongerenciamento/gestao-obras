import { Header } from "@/components/layout/Header";
import { ReimbursementsView } from "@/components/reimbursements/ReimbursementsView";
import { listMyReports } from "@/lib/api/reimbursements";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Reembolso é aberto a QUALQUER usuário autenticado — sem checagem de
// módulo aqui (RLS de reimbursement_reports já garante que cada um só vê
// os próprios relatórios). O link "Ver aprovações" é a exceção: só aparece
// pra quem tem o módulo 'financeiro' ou é master (mesma regra de /reembolso/aprovacoes).
export default async function ReimbursementsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [reports, userModules, { data: isMaster }] = await Promise.all([
    listMyReports(),
    listUserModules(),
    supabase.rpc("is_master"),
  ]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header breadcrumb={[{ label: "Início", href: "/" }, { label: "Reembolso" }]} userEmail={user?.email} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <ReimbursementsView
          reports={reports}
          hasApprovalAccess={userModules.includes("financeiro") || isMaster === true}
        />
      </main>
    </div>
  );
}
