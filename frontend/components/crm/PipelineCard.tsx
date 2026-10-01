"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import type { PipelineCardData } from "@/types/pipeline";

interface PipelineCardProps {
  card: PipelineCardData;
  draggable: boolean;
}

const CLICK_MOVE_THRESHOLD_PX = 5;

// iso é "YYYY-MM-DD" (coluna `date`, sem timezone) — monta o texto direto dos
// componentes pra não passar por new Date() e vazar timezone do browser.
function formatDatePtBR(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

export function PipelineCard({ card, draggable }: PipelineCardProps) {
  const router = useRouter();
  const mouseDownPos = useRef<{ x: number; y: number } | null>(null);
  const initial = card.ownerDisplayName.charAt(0).toUpperCase();

  function handleMouseDown(e: React.MouseEvent) {
    mouseDownPos.current = { x: e.clientX, y: e.clientY };
  }

  function handleMouseUp(e: React.MouseEvent) {
    const start = mouseDownPos.current;
    mouseDownPos.current = null;
    if (!start) return;
    const distance = Math.hypot(e.clientX - start.x, e.clientY - start.y);
    if (distance < CLICK_MOVE_THRESHOLD_PX) {
      router.push(`/projetos/${card.id}/comercial`);
    }
  }

  function handleDragStart(e: React.DragEvent<HTMLDivElement>) {
    e.dataTransfer.setData("text/project-id", card.id);
    e.dataTransfer.effectAllowed = "move";
  }

  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? handleDragStart : undefined}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      role="link"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") router.push(`/projetos/${card.id}/comercial`);
      }}
      className={`flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-3 transition-colors hover:border-pmon-yellow hover:shadow-md cursor-pointer ${draggable ? "active:cursor-grabbing" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-black">{card.name}</p>
          <p className="text-xs text-black/50">{card.clientName ?? "Sem cliente vinculado"}</p>
        </div>
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-pmon-yellow text-[10px] font-semibold text-pmon-black">
          {initial}
        </span>
      </div>

      {(card.pipelineStage === "prospect" || card.pipelineStage === "negociacao") && (
        <p className="text-xs text-black/40">
          {card.daysInStage === null
            ? "—"
            : `${card.daysInStage} dia${card.daysInStage === 1 ? "" : "s"} nesta etapa`}
        </p>
      )}

      {card.pipelineStage === "proposta" && (
        <p className={`text-xs ${card.proposalValidUntilExpired ? "font-medium text-red-600" : "text-black/40"}`}>
          {card.proposalValidUntil ? `Válida até ${formatDatePtBR(card.proposalValidUntil)}` : "—"}
        </p>
      )}

      {card.pipelineStage === "fechado_ganho" && <p className="text-xs text-green-700">Contrato ativo</p>}

      {card.pipelineStage === "fechado_perdido" && (
        <p className="text-xs text-black/40">{card.lostReason ?? "Motivo não informado"}</p>
      )}
    </div>
  );
}
