"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { NewReportForm } from "@/components/reimbursements/NewReportForm";
import type { ReimbursementReportStatus } from "@/types/reimbursement";
import type { ReportWithTotal } from "@/lib/api/reimbursements";

const STATUS_LABEL: Record<ReimbursementReportStatus, string> = {
  rascunho: "Rascunho",
  enviado: "Enviado",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

const STATUS_BADGE: Record<ReimbursementReportStatus, string> = {
  rascunho: "bg-black/5 text-black/60",
  enviado: "bg-blue-50 text-blue-700",
  aprovado: "bg-green-50 text-green-700",
  rejeitado: "bg-red-50 text-red-700",
};

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatDatePtBR(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

interface ReimbursementsViewProps {
  reports: ReportWithTotal[];
  hasApprovalAccess: boolean;
}

export function ReimbursementsView({ reports, hasApprovalAccess }: ReimbursementsViewProps) {
  const router = useRouter();
  const [formOpen, setFormOpen] = useState(false);

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-black">Reembolso</h1>
        <div className="flex items-center gap-4">
          {hasApprovalAccess && (
            <Link href="/reembolso/aprovacoes" className="text-sm font-medium text-black/60 hover:text-black">
              Ver aprovações →
            </Link>
          )}
          <Button onClick={() => setFormOpen((open) => !open)}>
            {formOpen ? "Cancelar" : "Novo relatório"}
          </Button>
        </div>
      </div>

      {formOpen && (
        <NewReportForm
          onCreated={(reportId) => {
            setFormOpen(false);
            router.push(`/reembolso/${reportId}`);
          }}
        />
      )}

      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="rounded-t-lg border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="rounded-tl-lg px-4 py-3 font-medium">Período</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="rounded-tr-lg px-4 py-3 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.id} className="border-b border-black/5 last:border-0 hover:bg-black/[0.02]">
                <td className="px-4 py-3">
                  <Link href={`/reembolso/${report.id}`} className="text-black hover:underline">
                    {formatDatePtBR(report.periodStart)} – {formatDatePtBR(report.periodEnd)}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_BADGE[report.status]}`}>
                    {STATUS_LABEL[report.status]}
                  </span>
                </td>
                <td className="px-4 py-3 text-black">{formatBRL(report.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {reports.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-black/50">Nenhum relatório de reembolso ainda.</p>
        )}
      </div>
    </>
  );
}
