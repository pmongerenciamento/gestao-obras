"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { IconTrash } from "@tabler/icons-react";
import type { Study } from "@/types/pre-planejamento";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { NewStudyModal } from "@/components/pre-planejamento/NewStudyModal";
import { deleteStudy } from "@/lib/api/pre-planejamento-mutations";

interface StudiesListProps {
  projectId: string;
  studies: Study[];
}

function formatDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR");
}

export function StudiesList({ projectId, studies }: StudiesListProps) {
  const router = useRouter();
  const [newStudyOpen, setNewStudyOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Study | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleConfirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteStudy(projectId, deleteTarget.id);
      router.refresh();
      setDeleteTarget(null);
    } catch {
      setDeleteError("Não foi possível excluir o cenário. Tente novamente.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-black">Pré-planejamento</h1>
        <Button onClick={() => setNewStudyOpen(true)}>Novo cenário</Button>
      </div>

      {studies.length === 0 ? (
        <p className="text-sm text-black/50">Nenhum cenário ainda. Clique em &quot;Novo cenário&quot; pra começar.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {studies.map((study) => (
            <div
              key={study.id}
              className="group relative rounded-lg border border-black/10 bg-white p-4 transition-colors hover:border-pmon-yellow"
            >
              <Link href={`/projetos/${projectId}/pre-planejamento/${study.id}/calendario`}>
                <h3 className="font-semibold text-black">{study.name}</h3>
                <p className="text-sm text-black/50">Início: {formatDate(study.startDate)}</p>
              </Link>
              <button
                type="button"
                onClick={() => setDeleteTarget(study)}
                className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full text-black/40 hover:bg-red-50 hover:text-red-600"
              >
                <IconTrash size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      <NewStudyModal open={newStudyOpen} projectId={projectId} onClose={() => setNewStudyOpen(false)} />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir cenário"
        description={`Tem certeza que deseja excluir o cenário "${deleteTarget?.name}"? Esta ação não pode ser desfeita.`}
        confirmLabel="Excluir"
        loadingLabel="Excluindo..."
        isLoading={deleting}
        error={deleteError}
        onConfirm={handleConfirmDelete}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteError(null);
        }}
      />
    </>
  );
}
