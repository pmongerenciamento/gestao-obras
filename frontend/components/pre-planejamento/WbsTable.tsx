"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IconChevronDown, IconChevronRight, IconRefresh } from "@tabler/icons-react";
import type { Cycle, StudyDetail } from "@/types/pre-planejamento";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { saveCycles, saveWbsOverrides } from "@/lib/api/pre-planejamento-mutations";
import { computeSchedule, suggestPredecessors, type ScheduledCycle } from "@/lib/pre-planejamento/scheduler";

// Aba "Estrutura WBS": árvore de 3 níveis (Serviço → Grupo/Torre →
// Pavimento) montada a partir de study.services/floors/cycles — não cria
// nem remove pavimento aqui (isso continua só em "Serviços e lotes"), só
// edita duração das folhas e os predecessores (sim_wbs_overrides). ID
// sequencial e código WBS são recalculados a cada render (posição na árvore,
// não armazenados) — mesmo comportamento do Task ID do MS Project.

function sanitizeDigits(value: string): string {
  return value.replace(/\D/g, "");
}

function formatDate(date: Date): string {
  return date.toLocaleDateString("pt-BR");
}

interface FlatRow {
  key: string;
  id: number;
  wbs: string;
  level: 1 | 2 | 3;
  label: string;
  cycleId?: string;
  ancestorKeys: string[];
}

function buildRows(study: StudyDetail): FlatRow[] {
  const floorById = new Map(study.floors.map((f) => [f.id, f]));
  const cyclesByService = new Map<string, Cycle[]>();
  for (const cycle of study.cycles) {
    const list = cyclesByService.get(cycle.serviceId) ?? [];
    list.push(cycle);
    cyclesByService.set(cycle.serviceId, list);
  }

  const rows: FlatRow[] = [];
  let nextId = 1;

  const orderedServices = [...study.services].sort((a, b) => a.orderIndex - b.orderIndex);
  orderedServices.forEach((service, serviceIdx) => {
    const serviceCycles = cyclesByService.get(service.id) ?? [];
    if (serviceCycles.length === 0) return;

    const serviceWbs = `${serviceIdx + 1}`;
    const serviceKey = `service:${service.id}`;
    rows.push({ key: serviceKey, id: nextId++, wbs: serviceWbs, level: 1, label: service.name, ancestorKeys: [] });

    const sortedCycles = [...serviceCycles].sort(
      (a, b) => (floorById.get(a.floorId)?.orderIndex ?? 0) - (floorById.get(b.floorId)?.orderIndex ?? 0),
    );
    const groupOrder: string[] = [];
    const cyclesByGroup = new Map<string, Cycle[]>();
    for (const cycle of sortedCycles) {
      const groupName = floorById.get(cycle.floorId)?.groupName ?? "";
      if (!cyclesByGroup.has(groupName)) {
        cyclesByGroup.set(groupName, []);
        groupOrder.push(groupName);
      }
      cyclesByGroup.get(groupName)!.push(cycle);
    }

    groupOrder.forEach((groupName, groupIdx) => {
      const groupWbs = `${serviceWbs}.${groupIdx + 1}`;
      const groupKey = `group:${service.id}:${groupName}`;
      rows.push({
        key: groupKey,
        id: nextId++,
        wbs: groupWbs,
        level: 2,
        label: groupName,
        ancestorKeys: [serviceKey],
      });

      cyclesByGroup.get(groupName)!.forEach((cycle, floorIdx) => {
        const floor = floorById.get(cycle.floorId);
        rows.push({
          key: `cycle:${cycle.id}`,
          id: nextId++,
          wbs: `${groupWbs}.${floorIdx + 1}`,
          level: 3,
          label: floor?.floorName ?? "—",
          cycleId: cycle.id,
          ancestorKeys: [serviceKey, groupKey],
        });
      });
    });
  });

  return rows;
}

function summarizeRow(
  row: FlatRow,
  allRows: FlatRow[],
  schedule: Map<string, ScheduledCycle>,
): { start: Date; end: Date } | null {
  const descendantCycleIds = allRows
    .filter((r) => r.level === 3 && r.wbs.startsWith(`${row.wbs}.`))
    .map((r) => r.cycleId)
    .filter((id): id is string => Boolean(id));

  const scheduled = descendantCycleIds.map((id) => schedule.get(id)).filter((s): s is ScheduledCycle => Boolean(s));
  if (scheduled.length === 0) return null;

  return {
    start: new Date(Math.min(...scheduled.map((s) => s.start.getTime()))),
    end: new Date(Math.max(...scheduled.map((s) => s.end.getTime()))),
  };
}

export function WbsTable() {
  const router = useRouter();
  const { projectId, study } = useStudy();

  const [durations, setDurations] = useState<Record<string, number>>(() =>
    Object.fromEntries(study.cycles.map((c) => [c.id, c.durationDays])),
  );
  const [predecessors, setPredecessors] = useState<Record<string, string[]>>(() => {
    const map: Record<string, string[]> = {};
    for (const link of study.predecessors) {
      const list = map[link.cycleId] ?? [];
      list.push(link.predecessorId);
      map[link.cycleId] = list;
    }
    return map;
  });
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmGenerate, setConfirmGenerate] = useState(false);

  // Estudo "ao vivo" com as edições locais ainda não salvas — Início/Término
  // recalculam na hora, mesmo comportamento do MS Project.
  const liveStudy: StudyDetail = useMemo(
    () => ({
      ...study,
      cycles: study.cycles.map((c) => ({ ...c, durationDays: durations[c.id] ?? c.durationDays })),
      predecessors: Object.entries(predecessors).flatMap(([cycleId, predecessorIds]) =>
        predecessorIds.map((predecessorId) => ({ cycleId, predecessorId })),
      ),
    }),
    [study, durations, predecessors],
  );

  const schedule = useMemo(() => computeSchedule(liveStudy), [liveStudy]);
  const rows = useMemo(() => buildRows(liveStudy), [liveStudy]);
  const rowById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);
  const rowByCycleId = useMemo(
    () => new Map(rows.filter((r) => r.cycleId).map((r) => [r.cycleId as string, r])),
    [rows],
  );
  const visibleRows = rows.filter((r) => !r.ancestorKeys.some((k) => collapsed.has(k)));

  function toggleCollapse(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleDurationChange(cycleId: string, value: string) {
    const digits = sanitizeDigits(value);
    setDurations((prev) => ({ ...prev, [cycleId]: digits ? Number(digits) : 1 }));
  }

  function handlePredecessorsChange(cycleId: string, value: string) {
    const resolved = value
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => rowById.get(Number(s))?.cycleId)
      .filter((id): id is string => Boolean(id) && id !== cycleId);
    setPredecessors((prev) => ({ ...prev, [cycleId]: resolved }));
  }

  function handleGenerate() {
    const hasExisting = Object.values(predecessors).some((list) => list.length > 0);
    if (hasExisting) {
      setConfirmGenerate(true);
      return;
    }
    doGenerate();
  }

  function doGenerate() {
    const suggestions = suggestPredecessors(study);
    const map: Record<string, string[]> = {};
    for (const suggestion of suggestions) {
      const list = map[suggestion.cycleId] ?? [];
      list.push(suggestion.predecessorId);
      map[suggestion.cycleId] = list;
    }
    setPredecessors(map);
    setConfirmGenerate(false);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await saveCycles(projectId, study.id, {
        services: study.services.map((s) => ({
          id: s.id,
          name: s.name,
          color: s.color,
          orderIndex: s.orderIndex,
          lagDays: s.lagDays,
        })),
        floors: study.floors.map((f) => ({
          id: f.id,
          groupName: f.groupName,
          floorName: f.floorName,
          orderIndex: f.orderIndex,
        })),
        cycles: study.cycles.map((c) => ({
          serviceIndex: study.services.findIndex((s) => s.id === c.serviceId),
          floorIndex: study.floors.findIndex((f) => f.id === c.floorId),
          durationDays: durations[c.id] ?? c.durationDays,
        })),
      });
      await saveWbsOverrides(projectId, study.id, {
        overrides: Object.entries(predecessors).map(([cycleId, predecessorIds]) => ({ cycleId, predecessorIds })),
      });
      router.refresh();
    } catch {
      setError("Não foi possível salvar a estrutura WBS. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  function focusCell(rowIndex: number, col: "duration" | "predecessors") {
    const el = document.querySelector<HTMLInputElement>(`input[data-row="${rowIndex}"][data-col="${col}"]`);
    el?.focus();
  }

  function handleKeyDown(
    e: React.KeyboardEvent<HTMLInputElement>,
    rowIndex: number,
    col: "duration" | "predecessors",
  ) {
    if (e.key === "Enter" || e.key === "ArrowDown") {
      e.preventDefault();
      focusCell(rowIndex + 1, col);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusCell(rowIndex - 1, col);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleGenerate}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15"
        >
          <IconRefresh size={16} /> Gerar estrutura automática
        </button>
        <span className="ml-1 text-xs text-black/40">
          Predecessores por ID separados por ; (ex.: 5;3) · Tab / Enter / setas navegam entre células
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-black/10 bg-white">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
              <th className="w-12 px-2 py-2 text-left">ID</th>
              <th className="w-20 px-2 py-2 text-left">WBS</th>
              <th className="px-3 py-2 text-left">Nome da tarefa</th>
              <th className="w-24 px-2 py-2 text-left">Duração</th>
              <th className="w-28 px-2 py-2 text-left">Predecessores</th>
              <th className="w-28 px-2 py-2 text-left">Início</th>
              <th className="w-28 px-2 py-2 text-left">Término</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => {
              const scheduled = row.cycleId ? schedule.get(row.cycleId) : undefined;
              const summary = row.level !== 3 ? summarizeRow(row, rows, schedule) : null;
              return (
                <tr
                  key={row.key}
                  className={`border-b border-black/5 ${
                    row.level === 1 ? "bg-black/[0.03] font-semibold" : row.level === 2 ? "bg-black/[0.015]" : ""
                  }`}
                >
                  <td className="px-2 py-1.5 text-black/50">{row.id}</td>
                  <td className="px-2 py-1.5 text-black/50">{row.wbs}</td>
                  <td className="px-3 py-1.5 text-black" style={{ paddingLeft: 12 + (row.level - 1) * 16 }}>
                    <div className="flex items-center gap-1">
                      {row.level < 3 && (
                        <button
                          type="button"
                          onClick={() => toggleCollapse(row.key)}
                          className="text-black/40 hover:text-black"
                        >
                          {collapsed.has(row.key) ? <IconChevronRight size={14} /> : <IconChevronDown size={14} />}
                        </button>
                      )}
                      {row.label}
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    {row.cycleId ? (
                      <input
                        type="text"
                        inputMode="numeric"
                        data-row={rowIndex}
                        data-col="duration"
                        value={durations[row.cycleId] ?? ""}
                        onChange={(e) => handleDurationChange(row.cycleId as string, e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, rowIndex, "duration")}
                        className="w-16 rounded border border-black/20 px-2 py-1 text-center"
                      />
                    ) : (
                      <span className="text-black/30">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    {row.cycleId ? (
                      <input
                        type="text"
                        data-row={rowIndex}
                        data-col="predecessors"
                        defaultValue={(predecessors[row.cycleId] ?? [])
                          .map((id) => rowByCycleId.get(id)?.id)
                          .filter((id): id is number => id !== undefined)
                          .join(";")}
                        onBlur={(e) => handlePredecessorsChange(row.cycleId as string, e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, rowIndex, "predecessors")}
                        className="w-20 rounded border border-black/20 px-2 py-1 text-center"
                      />
                    ) : (
                      <span className="text-black/30">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-black/70">
                    {scheduled ? formatDate(scheduled.start) : summary ? formatDate(summary.start) : "—"}
                  </td>
                  <td className="px-2 py-1.5 text-black/70">
                    {scheduled ? formatDate(scheduled.end) : summary ? formatDate(summary.end) : "—"}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-black/50">
                  Nenhuma tarefa ainda — cadastre serviços e pavimentos na aba &quot;Serviços e lotes&quot;.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <Button onClick={handleSave} isLoading={saving} className="self-start">
        {saving ? "Salvando..." : "Salvar"}
      </Button>

      <ConfirmDialog
        open={confirmGenerate}
        title="Gerar estrutura automática"
        description="Já existem predecessores definidos. Gerar a estrutura automática vai substituir todos pelos sugeridos (encadeamento por ordem de pavimento)."
        confirmLabel="Substituir"
        onConfirm={doGenerate}
        onCancel={() => setConfirmGenerate(false)}
      />
    </div>
  );
}
