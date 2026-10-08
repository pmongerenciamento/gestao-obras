import { redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { ApprovalsView } from "@/components/reimbursements/ApprovalsView";
import { listPendingApprovals } from "@/lib/api/reimbursements";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

// Fila de aprovação: entra quem tem o módulo 'financeiro' ou é master
// (is_master(), 043 — mesma chamada de lib/api/access.ts). A partir da 052,
// aprovar e rejeitar são só do master; o financeiro continua lendo a fila.
// RLS é quem de fato protege os dados; isto só evita renderizar uma tela
// vazia/quebrada pra quem não tem acesso.
export default async function ReimbursementApprovalsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [userModules, { data: isMaster }] = await Promise.all([listUserModules(), supabase.rpc("is_master")]);
  if (!userModules.includes("financeiro") && isMaster !== true) redirect("/reembolso");

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
