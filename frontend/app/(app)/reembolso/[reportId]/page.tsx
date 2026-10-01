import { notFound } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { ReportDetailView } from "@/components/reimbursements/ReportDetailView";
import {
  getReport,
  listActiveRateRules,
  listCostCenters,
  listProjectsForSelect,
  listReportItems,
} from "@/lib/api/reimbursements";
import { createClient } from "@/lib/supabase/server";

interface ReportPageProps {
  params: Promise<{ reportId: string }>;
}

export default async function ReportPage({ params }: ReportPageProps) {
  const { reportId } = await params;

  const report = await getReport(reportId);
  if (!report) notFound();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [items, costCenters, rateRules, projects] = await Promise.all([
    listReportItems(reportId),
    listCostCenters(),
    listActiveRateRules(),
    listProjectsForSelect(),
  ]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        breadcrumb={[
          { label: "Início", href: "/" },
          { label: "Reembolso", href: "/reembolso" },
          { label: "Relatório" },
        ]}
        userEmail={user?.email}
      />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
        <ReportDetailView
          report={report}
          items={items}
          costCenters={costCenters}
          rateRules={rateRules}
          projects={projects}
        />
      </main>
    </div>
  );
}
