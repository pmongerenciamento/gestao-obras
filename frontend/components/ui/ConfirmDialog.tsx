"use client";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  loadingLabel?: string;
  cancelLabel?: string;
  isLoading?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

// Modal genérico de confirmação (não específico de projeto) — pra reusar em
// futuras ações destrutivas (excluir tarefa, snapshot, etc).
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  loadingLabel,
  cancelLabel = "Cancelar",
  isLoading = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-black">{title}</h2>
        <p className="mt-2 text-sm text-black/60">{description}</p>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? (loadingLabel ?? confirmLabel) : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
