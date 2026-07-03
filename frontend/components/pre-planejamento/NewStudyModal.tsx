"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { createStudy } from "@/lib/api/pre-planejamento-mutations";

interface NewStudyModalProps {
  open: boolean;
  projectId: string;
  onClose: () => void;
}

export function NewStudyModal({ open, projectId, onClose }: NewStudyModalProps) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function handleClose() {
    setName("");
    setStartDate("");
    setError(null);
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const estudoId = await createStudy(projectId, { name, startDate });
      handleClose();
      router.push(`/projetos/${projectId}/pre-planejamento/${estudoId}/calendario`);
      router.refresh();
    } catch {
      setError("Não foi possível criar o cenário. Tente novamente.");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={handleClose}>
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-black">Novo cenário</h2>
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <Input
            id="studyName"
            label="Nome do cenário"
            variant="light"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            id="studyStartDate"
            label="Data de início"
            type="date"
            variant="light"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="mt-2 flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              disabled={submitting}
              className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancelar
            </button>
            <Button type="submit" isLoading={submitting}>
              {submitting ? "Criando..." : "Criar cenário"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
