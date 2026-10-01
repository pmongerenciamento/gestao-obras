import Link from "next/link";
import type { PendingApprovalReport } from "@/lib/api/reimbursements";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatDatePtBR(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

interface ApprovalsViewProps {
  reports: PendingApprovalReport[];
}

// Fila de aprovação do financeiro: só relatórios 'enviado', mais antigos
// primeiro. Sem formulário/ação nesta tela — a ação (aprovar/rejeitar) mora
// no detalhe (ApprovalDetailView).
export function ApprovalsView({ reports }: ApprovalsViewProps) {
  return (
    <>
      <h1 className="mb-6 text-xl font-semibold text-black">Aprovações de reembolso</h1>

      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="rounded-t-lg border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="rounded-tl-lg px-4 py-3 font-medium">Solicitante</th>
              <th className="px-4 py-3 font-medium">Período</th>
              <th className="rounded-tr-lg px-4 py-3 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.id} className="border-b border-black/5 last:border-0 hover:bg-black/[0.02]">
                <td className="px-4 py-3">
                  <Link href={`/reembolso/aprovacoes/${report.id}`} className="text-black hover:underline">
                    {report.requesterName}
                  </Link>
                </td>
                <td className="px-4 py-3 text-black/70">
                  {formatDatePtBR(report.periodStart)} – {formatDatePtBR(report.periodEnd)}
                </td>
                <td className="px-4 py-3 text-black">{formatBRL(report.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {reports.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-black/50">Nenhum relatório aguardando aprovação.</p>
        )}
      </div>
    </>
  );
}
