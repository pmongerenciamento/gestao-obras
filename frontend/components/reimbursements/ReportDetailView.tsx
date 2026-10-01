"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { NewItemForm } from "@/components/reimbursements/NewItemForm";
import { reopenReport, submitForApproval } from "@/lib/api/reimbursement-mutations";
import type {
  CostCenter,
  ProjectOption,
  RateRule,
  ReimbursementItem,
  ReimbursementItemType,
  ReimbursementReport,
  ReimbursementReportStatus,
} from "@/types/reimbursement";

const STATUS_LABEL: Record<ReimbursementReportStatus, string> = {
  rascunho: "Rascunho",
  enviado: "Enviado",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

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

interface ReportDetailViewProps {
  report: ReimbursementReport;
  items: ReimbursementItem[];
  costCenters: CostCenter[];
  rateRules: RateRule[];
  projects: ProjectOption[];
}

export function ReportDetailView({ report, items, costCenters, rateRules, projects }: ReportDetailViewProps) {
  const router = useRouter();
  const [itemFormOpen, setItemFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [confirmSubmitOpen, setConfirmSubmitOpen] = useState(false);

  const isDraft = report.status === "rascunho";
  const isRejected = report.status === "rejeitado";
  const total = items.reduce((sum, item) => sum + item.totalAmount, 0);

  async function handleSubmitForApproval() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await submitForApproval(report.id);
      setConfirmSubmitOpen(false);
      router.refresh();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível enviar para aprovação. Tente novamente.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReopen() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await reopenReport(report.id);
      router.refresh();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível reabrir o relatório. Tente novamente.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between rounded-lg border border-black/10 bg-white p-6">
        <div>
          <p className="text-xs text-black/50">Período</p>
          <p className="text-sm font-medium text-black">
            {formatDatePtBR(report.periodStart)} – {formatDatePtBR(report.periodEnd)}
          </p>
        </div>
        <span className="rounded-full bg-black/5 px-3 py-1 text-xs font-medium text-black/60">
          {STATUS_LABEL[report.status]}
        </span>
      </div>

      {isRejected && (
        <div className="flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          {report.rejectionReason && (
            <div>
              <p className="text-xs text-red-700/70">Motivo da rejeição</p>
              <p className="text-sm text-red-700">{report.rejectionReason}</p>
            </div>
          )}
          <Button onClick={handleReopen} disabled={submitting} isLoading={submitting} className="w-fit">
            {submitting ? "Reabrindo..." : "Corrigir e reenviar"}
          </Button>
        </div>
      )}

      {!isDraft && !isRejected && (
        <p className="text-sm text-black/50">
          Este relatório não está mais em rascunho — somente leitura.
        </p>
      )}

      {isDraft && (
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-black">Itens</h2>
          <Button onClick={() => setItemFormOpen((open) => !open)}>
            {itemFormOpen ? "Cancelar" : "Adicionar item"}
          </Button>
        </div>
      )}

      {itemFormOpen && (
        <NewItemForm
          reportId={report.id}
          costCenters={costCenters}
          rateRules={rateRules}
          projects={projects}
          onCreated={() => {
            setItemFormOpen(false);
            router.refresh();
          }}
        />
      )}

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
        {items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-black/50">Nenhum item lançado ainda.</p>
        )}
      </div>

      {submitError && !confirmSubmitOpen && <p className="text-sm text-red-500">{submitError}</p>}

      {isDraft && items.length > 0 && (
        <Button onClick={() => setConfirmSubmitOpen(true)} className="w-fit">
          Enviar para aprovação
        </Button>
      )}

      <ConfirmDialog
        open={confirmSubmitOpen}
        title="Enviar para aprovação"
        description="Confirma o reenvio deste relatório para aprovação? Depois de enviado, ele vira somente leitura até ser aprovado ou rejeitado."
        confirmLabel="Enviar"
        loadingLabel="Enviando..."
        isLoading={submitting}
        error={submitError}
        onConfirm={handleSubmitForApproval}
        onCancel={() => {
          setConfirmSubmitOpen(false);
          setSubmitError(null);
        }}
      />
    </div>
  );
}
