"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { moveToNegotiation, markAsLost } from "@/lib/api/proposal-mutations";
import { PIPELINE_STAGES } from "@/lib/pipeline-stages";
import { CloseDealForm } from "@/components/proposals/CloseDealForm";
import type { Proposal, ProposalStatus, PaymentType } from "@/types/proposal";
import type { PipelineStage } from "@/types/crm";
import type { Team } from "@/types/team";

const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string> = {
  rascunho: "Rascunho",
  enviada: "Enviada",
  em_negociacao: "Em negociação",
  aceita: "Aceita",
  recusada: "Recusada",
};

const PAYMENT_TYPE_LABEL: Record<PaymentType, string> = {
  mensal_recorrente: "Mensal recorrente",
  parcela_unica: "Parcela única",
  parcelado: "Parcelado",
};

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatDatePtBR(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function stageLabel(stage: PipelineStage): string {
  return PIPELINE_STAGES.find((s) => s.stage === stage)?.label ?? stage;
}

interface ProposalDetailsProps {
  proposal: Proposal;
  pipelineStage: PipelineStage;
  projectId: string;
  teams: Team[];
  onUpdated: () => void;
  onClosed: () => void;
}

export function ProposalDetails({
  proposal,
  pipelineStage,
  projectId,
  teams,
  onUpdated,
  onClosed,
}: ProposalDetailsProps) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lostReasonOpen, setLostReasonOpen] = useState(false);
  const [lostReason, setLostReason] = useState("");
  const [closeDealOpen, setCloseDealOpen] = useState(false);

  const canMoveToNegotiation = pipelineStage === "proposta";
  const canMarkAsLost = pipelineStage === "proposta" || pipelineStage === "negociacao";
  const canCloseDeal = pipelineStage === "proposta" || pipelineStage === "negociacao";

  async function handleMoveToNegotiation() {
    setActionError(null);
    setBusy(true);
    try {
      await moveToNegotiation(proposal.id, projectId);
      onUpdated();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Não foi possível mover para negociação. Tente novamente.",
      );
      setBusy(false);
    }
  }

  async function handleConfirmLost() {
    if (!lostReason.trim()) {
      setActionError("Informe o motivo da perda.");
      return;
    }
    setActionError(null);
    setBusy(true);
    try {
      await markAsLost(proposal.id, projectId, lostReason.trim());
      onUpdated();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Não foi possível marcar como perdido. Tente novamente.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 rounded-lg border border-black/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-black/50">Etapa atual</p>
          <p className="text-sm font-medium text-black">{stageLabel(pipelineStage)}</p>
        </div>
        <span className="rounded-full bg-black/5 px-3 py-1 text-xs font-medium text-black/60">
          Proposta v{proposal.version} — {PROPOSAL_STATUS_LABEL[proposal.status]}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-black/50">Tipo de serviço</p>
          <p className="text-sm text-black">{proposal.serviceTypeName ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs text-black/50">Valor</p>
          <p className="text-sm text-black">{formatBRL(proposal.value)}</p>
        </div>
        <div>
          <p className="text-xs text-black/50">Forma de pagamento</p>
          <p className="text-sm text-black">
            {PAYMENT_TYPE_LABEL[proposal.paymentType]}
            {proposal.paymentType === "parcelado" && proposal.installmentsCount
              ? ` (${proposal.installmentsCount}x)`
              : ""}
          </p>
        </div>
        <div>
          <p className="text-xs text-black/50">Válida até</p>
          <p className="text-sm text-black">
            {proposal.validUntil ? formatDatePtBR(proposal.validUntil) : "—"}
          </p>
        </div>
      </div>

      {proposal.scopeDescription && (
        <div>
          <p className="text-xs text-black/50">Descrição do escopo</p>
          <p className="whitespace-pre-wrap text-sm text-black">{proposal.scopeDescription}</p>
        </div>
      )}

      {proposal.status === "recusada" && proposal.lostReason && (
        <div>
          <p className="text-xs text-black/50">Motivo da perda</p>
          <p className="text-sm text-black">{proposal.lostReason}</p>
        </div>
      )}

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      {(canMoveToNegotiation || canMarkAsLost || canCloseDeal) && (
        <div className="flex flex-wrap items-center gap-3 border-t border-black/10 pt-4">
          {canMoveToNegotiation && (
            <Button onClick={handleMoveToNegotiation} disabled={busy} isLoading={busy}>
              Mover para Negociação
            </Button>
          )}

          {canCloseDeal && !closeDealOpen && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setCloseDealOpen(true)}
              className="rounded-md border border-green-200 px-4 py-2 font-semibold text-green-700 transition-colors hover:bg-green-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Fechar (ganho)
            </button>
          )}

          {canMarkAsLost && !lostReasonOpen && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setLostReasonOpen(true)}
              className="rounded-md border border-red-200 px-4 py-2 font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Marcar como perdido
            </button>
          )}
        </div>
      )}

      {closeDealOpen && (
        <CloseDealForm
          projectId={projectId}
          teams={teams}
          onClosed={onClosed}
          onCancel={() => setCloseDealOpen(false)}
        />
      )}

      {lostReasonOpen && (
        <div className="flex flex-col gap-2 rounded-md border border-dashed border-red-200 p-4">
          <label htmlFor="lostReason" className="text-sm text-black/70">
            Motivo da perda
          </label>
          <textarea
            id="lostReason"
            rows={3}
            value={lostReason}
            onChange={(e) => setLostReason(e.target.value)}
            className="rounded-md border border-black/20 bg-white px-3 py-2 text-black placeholder:text-black/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={handleConfirmLost}
              className="rounded-md bg-red-600 px-4 py-2 font-semibold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Confirmando..." : "Confirmar perda"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setLostReasonOpen(false);
                setLostReason("");
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
