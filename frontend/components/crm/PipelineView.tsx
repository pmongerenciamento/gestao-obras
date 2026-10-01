"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PipelineColumn } from "@/types/pipeline";
import type { Client } from "@/types/client";
import { Button } from "@/components/ui/Button";
import { PipelineBoard } from "@/components/crm/PipelineBoard";
import { NewProspectForm } from "@/components/crm/NewProspectForm";

interface PipelineViewProps {
  columns: PipelineColumn[];
  clients: Client[];
  suggestedClientCode: string;
}

export function PipelineView({ columns, clients, suggestedClientCode }: PipelineViewProps) {
  const router = useRouter();
  const [formOpen, setFormOpen] = useState(false);

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-black">Pipeline</h1>
        <Button onClick={() => setFormOpen((open) => !open)}>{formOpen ? "Cancelar" : "Novo prospect"}</Button>
      </div>

      {formOpen && (
        <NewProspectForm
          clients={clients}
          suggestedClientCode={suggestedClientCode}
          onCreated={() => {
            setFormOpen(false);
            router.refresh();
          }}
        />
      )}

      <PipelineBoard columns={columns} />
    </>
  );
}
