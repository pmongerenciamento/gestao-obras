"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IconTrash } from "@tabler/icons-react";
import type { Holiday } from "@/types/pre-planejamento";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { MiniCalendar } from "@/components/pre-planejamento/MiniCalendar";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { updateStudy } from "@/lib/api/pre-planejamento-mutations";

// Aba "Calendário": feriados nacionais pré-cadastrados (na criação do
// estudo, só leitura — não fazem sentido remover, são fixos por lei) +
// personalizados (editáveis/removíveis a qualquer momento, item 48 do
// plano) — qualquer edição aqui recalcula a Linha de Balanço
// automaticamente, porque aquela aba sempre lê os feriados mais recentes.

function formatDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR");
}

export function HolidayCalendar() {
  const router = useRouter();
  const { projectId, study } = useStudy();
  const [holidays, setHolidays] = useState<Holiday[]>(
    [...study.holidays].sort((a, b) => a.date.localeCompare(b.date)),
  );
  const [newDate, setNewDate] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleAdd() {
    if (!newDate || !newDescription.trim()) return;
    setHolidays((prev) =>
      [...prev, { id: crypto.randomUUID(), date: newDate, description: newDescription.trim(), isNational: false }].sort(
        (a, b) => a.date.localeCompare(b.date),
      ),
    );
    setNewDate("");
    setNewDescription("");
  }

  function handleRemove(id: string) {
    setHolidays((prev) => prev.filter((h) => h.id !== id));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await updateStudy(projectId, study.id, {
        name: study.name,
        startDate: study.startDate,
        holidays: holidays.map((h) => ({ date: h.date, description: h.description, isNational: h.isNational })),
      });
      router.refresh();
    } catch {
      setError("Não foi possível salvar o calendário. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  const nationalHolidays = holidays.filter((h) => h.isNational);
  const customHolidays = holidays.filter((h) => !h.isNational);

  return (
    <div className="grid grid-cols-[340px_1fr] items-start gap-6">
      <div className="rounded-lg border border-black/10 bg-white p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase text-black/50">Visão do mês</h2>
        <MiniCalendar initialMonth={study.startDate} holidays={holidays} />
      </div>

      <div className="flex flex-col gap-6">
        <div>
          <h2 className="mb-2 text-xs font-semibold uppercase text-black/50">Feriados nacionais (pré-cadastrados)</h2>
          <div className="flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-2">
            {nationalHolidays.map((holiday) => (
              <div
                key={holiday.id}
                className="flex items-center justify-between rounded-md bg-black/[0.02] px-3 py-2 text-sm"
              >
                <span className="w-24 shrink-0 text-black/60">{formatDate(holiday.date)}</span>
                <span className="flex-1 text-black">{holiday.description}</span>
                <span className="text-black/30" title="Feriado nacional — não pode ser removido">
                  🔒
                </span>
              </div>
            ))}
            {nationalHolidays.length === 0 && (
              <p className="px-3 py-4 text-center text-sm text-black/40">Nenhum feriado nacional.</p>
            )}
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-xs font-semibold uppercase text-black/50">Feriados personalizados</h2>
          <div className="flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-2">
            {customHolidays.map((holiday) => (
              <div
                key={holiday.id}
                className="flex items-center justify-between rounded-md bg-blue-50 px-3 py-2 text-sm"
              >
                <span className="w-24 shrink-0 text-black/60">{formatDate(holiday.date)}</span>
                <span className="flex-1 text-black">{holiday.description}</span>
                <button
                  type="button"
                  onClick={() => handleRemove(holiday.id)}
                  className="text-black/40 hover:text-red-600"
                >
                  <IconTrash size={16} />
                </button>
              </div>
            ))}
            {customHolidays.length === 0 && (
              <p className="px-3 py-4 text-center text-sm text-black/40">Nenhum feriado personalizado ainda.</p>
            )}
          </div>

          <div className="mt-3 flex items-end gap-3 rounded-lg border border-black/10 bg-white p-4">
            <Input
              id="newHolidayDate"
              label="Data"
              type="date"
              variant="light"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
            />
            <div className="flex-1">
              <Input
                id="newHolidayDescription"
                label="Descrição"
                variant="light"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={handleAdd}
              disabled={!newDate || !newDescription.trim()}
              className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Adicionar feriado
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <Button onClick={handleSave} isLoading={saving} className="self-start">
          {saving ? "Salvando..." : "Salvar calendário"}
        </Button>
      </div>
    </div>
  );
}
