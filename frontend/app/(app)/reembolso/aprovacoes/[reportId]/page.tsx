import { notFound, redirect } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { ApprovalDetailView } from "@/components/reimbursements/ApprovalDetailView";
import { getReport, listReportItems } from "@/lib/api/reimbursements";
import { listUserModules } from "@/lib/api/modules";
import { createClient } from "@/lib/supabase/server";

interface ApprovalDetailPageProps {
  params: Promise<{ reportId: string }>;
}

export default async function ApprovalDetailPage({ params }: ApprovalDetailPageProps) {
  const { reportId } = await params;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const userModules = await listUserModules();
  if (!userModules.includes("financeiro")) redirect("/reembolso");

  const report = await getReport(reportId);
  if (!report) notFound();

  const [items, requesterNameResult] = await Promise.all([
    listReportItems(reportId),
    supabase.rpc("profile_display_name", { p_profile_id: report.profileId }),
  ]);
  const requesterName = (requesterNameResult.data as string | null) ?? "—";

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[
          { label: "Início", href: "/" },
          { label: "Reembolso", href: "/reembolso" },
          { label: "Aprovações", href: "/reembolso/aprovacoes" },
          { label: requesterName },
        ]}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <ApprovalDetailView report={report} items={items} requesterName={requesterName} />
      </main>
    </div>
  );
}
