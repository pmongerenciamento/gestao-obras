"use client";

import { useState } from "react";
import type { PipelineColumn } from "@/types/pipeline";
import type { PipelineStage } from "@/types/crm";
import { PipelineCard } from "@/components/crm/PipelineCard";
import { updateProjectStage } from "@/lib/api/pipeline-mutations";

interface PipelineBoardProps {
  columns: PipelineColumn[];
}

const DROPPABLE_STAGES: PipelineStage[] = ["prospect", "proposta", "negociacao"];
const DRAGGABLE_STAGES: PipelineStage[] = ["prospect", "proposta", "negociacao"];

export function PipelineBoard({ columns: initialColumns }: PipelineBoardProps) {
  const [columns, setColumns] = useState(initialColumns);
  const [dragOverStage, setDragOverStage] = useState<PipelineStage | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDrop(projectId: string, toStage: PipelineStage) {
    setError(null);

    const fromColumn = columns.find((col) => col.cards.some((c) => c.id === projectId));
    const card = fromColumn?.cards.find((c) => c.id === projectId);
    if (!fromColumn || !card || fromColumn.stage === toStage) return;

    const previousColumns = columns;

    const movedCard = {
      ...card,
      pipelineStage: toStage,
      daysInStage: toStage === "prospect" || toStage === "negociacao" ? 0 : null,
      proposalValidUntil: null,
      proposalValidUntilExpired: false,
      lostReason: null,
    };

    setColumns((prev) =>
      prev.map((col) => {
        if (col.stage === fromColumn.stage) {
          return { ...col, cards: col.cards.filter((c) => c.id !== projectId) };
        }
        if (col.stage === toStage) {
          return { ...col, cards: [...col.cards, movedCard] };
        }
        return col;
      }),
    );

    try {
      await updateProjectStage(projectId, toStage);
    } catch (err) {
      setColumns(previousColumns);
      setError(err instanceof Error ? err.message : "Não foi possível mover o card. Tente novamente.");
    }
  }

  return (
    <div>
      {error && <p className="mb-3 text-sm text-red-500">{error}</p>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-5">
        {columns.map((column) => {
          const isDroppable = DROPPABLE_STAGES.includes(column.stage);
          const isDraggableColumn = DRAGGABLE_STAGES.includes(column.stage);
          const isDragOver = dragOverStage === column.stage;

          return (
            <div
              key={column.stage}
              onDragOver={
                isDroppable
                  ? (e) => {
                      e.preventDefault();
                      if (dragOverStage !== column.stage) setDragOverStage(column.stage);
                    }
                  : undefined
              }
              onDragLeave={
                isDroppable
                  ? () => setDragOverStage((current) => (current === column.stage ? null : current))
                  : undefined
              }
              onDrop={
                isDroppable
                  ? (e) => {
                      e.preventDefault();
                      setDragOverStage(null);
                      const projectId = e.dataTransfer.getData("text/project-id");
                      if (projectId) handleDrop(projectId, column.stage);
                    }
                  : undefined
              }
              className={`flex flex-col gap-3 rounded-lg p-3 transition-colors ${
                isDragOver ? "bg-pmon-yellow/20 ring-2 ring-pmon-yellow" : "bg-black/[0.03]"
              }`}
            >
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-black/70">{column.label}</h2>
                <span className="rounded-full bg-black/10 px-2 py-0.5 text-xs font-medium text-black/60">
                  {column.cards.length}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {column.cards.map((card) => (
                  <PipelineCard key={card.id} card={card} draggable={isDraggableColumn} />
                ))}
                {column.cards.length === 0 && (
                  <p className="rounded-md border border-dashed border-black/10 p-3 text-center text-xs text-black/30">
                    Nenhum projeto
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
