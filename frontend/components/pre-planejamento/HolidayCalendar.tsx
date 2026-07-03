"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IconTrash } from "@tabler/icons-react";
import type { Holiday } from "@/types/pre-planejamento";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { updateStudy } from "@/lib/api/pre-planejamento-mutations";

// Aba "Calendário": feriados nacionais pré-cadastrados (na criação do
// estudo) + personalizados, todos editáveis/removíveis a qualquer momento
// (item 48 do plano) — qualquer edição aqui recalcula a Linha de Balanço
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

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="px-4 py-3 font-medium">Data</th>
              <th className="px-4 py-3 font-medium">Descrição</th>
              <th className="px-4 py-3 font-medium">Tipo</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {holidays.map((holiday) => (
              <tr key={holiday.id} className="border-b border-black/5 last:border-0">
                <td className="px-4 py-3 text-black">{formatDate(holiday.date)}</td>
                <td className="px-4 py-3 text-black">{holiday.description}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      holiday.isNational ? "bg-pmon-yellow/20 text-pmon-black" : "bg-black/10 text-black/60"
                    }`}
                  >
                    {holiday.isNational ? "Nacional" : "Personalizado"}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => handleRemove(holiday.id)}
                    className="text-black/40 hover:text-red-600"
                  >
                    <IconTrash size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {holidays.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-black/50">
                  Nenhum feriado cadastrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-end gap-3 rounded-lg border border-black/10 bg-white p-4">
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

      {error && <p className="text-sm text-red-500">{error}</p>}

      <Button onClick={handleSave} isLoading={saving} className="self-start">
        {saving ? "Salvando..." : "Salvar calendário"}
      </Button>
    </div>
  );
}
