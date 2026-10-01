import { redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { ApprovalsView } from "@/components/reimbursements/ApprovalsView";
import { listPendingApprovals } from "@/lib/api/reimbursements";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Fila de aprovação: hoje só o módulo 'financeiro' tem
// has_permission('reimbursement_reports','write') (030), então checar o
// módulo aqui é equivalente — mesmo padrão de proxy já usado em
// ComercialPage/CrmPage (RLS é quem de fato protege os dados; isto só evita
// renderizar uma tela vazia/quebrada pra quem não tem acesso).
export default async function ReimbursementApprovalsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const userModules = await listUserModules();
  if (!userModules.includes("financeiro")) redirect("/reembolso");

  const reports = await listPendingApprovals();

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[
          { label: "Início", href: "/" },
          { label: "Reembolso", href: "/reembolso" },
          { label: "Aprovações" },
        ]}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <ApprovalsView reports={reports} />
      </main>
    </div>
  );
}
