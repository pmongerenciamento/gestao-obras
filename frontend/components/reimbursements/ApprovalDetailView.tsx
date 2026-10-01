"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { approveReport, rejectReport } from "@/lib/api/reimbursement-mutations";
import type { ReimbursementItem, ReimbursementItemType, ReimbursementReport } from "@/types/reimbursement";

const TYPE_LABEL: Record<ReimbursementItemType, string> = {
  deslocamento_escritorio: "Deslocamento Escritório",
  visita_cliente: "Visita a Cliente",
  visita_comercial: "Visita Comercial",
  alimentacao: "Alimentação",
  outros: "Outros",
};

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatDatePtBR(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

interface ApprovalDetailViewProps {
  report: ReimbursementReport;
  items: ReimbursementItem[];
  requesterName: string;
}

export function ApprovalDetailView({ report, items, requesterName }: ApprovalDetailViewProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const total = items.reduce((sum, item) => sum + item.totalAmount, 0);
  const canAct = report.status === "enviado";

  async function handleApprove() {
    setActionError(null);
    setBusy(true);
    try {
      await approveReport(report.id);
      router.push("/reembolso/aprovacoes");
      router.refresh();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Não foi possível aprovar. Tente novamente.",
      );
      setBusy(false);
    }
  }

  async function handleConfirmReject() {
    if (!rejectReason.trim()) {
      setActionError("Informe o motivo da rejeição.");
      return;
    }
    setActionError(null);
    setBusy(true);
    try {
      await rejectReport(report.id, rejectReason.trim());
      router.push("/reembolso/aprovacoes");
      router.refresh();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Não foi possível rejeitar. Tente novamente.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between rounded-lg border border-black/10 bg-white p-6">
        <div>
          <p className="text-xs text-black/50">Solicitante</p>
          <p className="text-sm font-medium text-black">{requesterName}</p>
        </div>
        <div>
          <p className="text-xs text-black/50">Período</p>
          <p className="text-sm font-medium text-black">
            {formatDatePtBR(report.periodStart)} – {formatDatePtBR(report.periodEnd)}
          </p>
        </div>
        <span className="rounded-full bg-black/5 px-3 py-1 text-xs font-medium text-black/60">
          {report.status === "enviado" ? "Aguardando aprovação" : report.status}
        </span>
      </div>

      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="rounded-t-lg border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="rounded-tl-lg px-4 py-3 font-medium">Data</th>
              <th className="px-4 py-3 font-medium">Tipo</th>
              <th className="px-4 py-3 font-medium">Descrição</th>
              <th className="px-4 py-3 font-medium">Projeto / Centro de custo</th>
              <th className="rounded-tr-lg px-4 py-3 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b border-black/5 last:border-0">
                <td className="px-4 py-3 text-black/70">{formatDatePtBR(item.expenseDate)}</td>
                <td className="px-4 py-3 text-black">{TYPE_LABEL[item.type]}</td>
                <td className="px-4 py-3 text-black/70">{item.description}</td>
                <td className="px-4 py-3 text-black/70">{item.projectName ?? item.costCenterName ?? "—"}</td>
                <td className="px-4 py-3 text-black">{formatBRL(item.totalAmount)}</td>
              </tr>
            ))}
          </tbody>
          {items.length > 0 && (
            <tfoot>
              <tr className="border-t border-black/10 bg-black/[0.02] font-semibold">
                <td className="px-4 py-3 text-black" colSpan={4}>
                  Total geral
                </td>
                <td className="px-4 py-3 text-black">{formatBRL(total)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      {canAct && (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleApprove} disabled={busy} isLoading={busy}>
            {busy ? "Aprovando..." : "Aprovar"}
          </Button>

          {!rejectOpen && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setRejectOpen(true)}
              className="rounded-md border border-red-200 px-4 py-2 font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Rejeitar
            </button>
          )}
        </div>
      )}

      {rejectOpen && (
        <div className="flex flex-col gap-2 rounded-md border border-dashed border-red-200 p-4">
          <label htmlFor="rejectReason" className="text-sm text-black/70">
            Motivo da rejeição
          </label>
          <textarea
            id="rejectReason"
            rows={3}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="rounded-md border border-black/20 bg-white px-3 py-2 text-black placeholder:text-black/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={handleConfirmReject}
              className="rounded-md bg-red-600 px-4 py-2 font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Confirmando..." : "Confirmar rejeição"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setRejectOpen(false);
                setRejectReason("");
                setActionError(null);
              }}
              className="text-sm text-black/50 hover:text-black/70"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
