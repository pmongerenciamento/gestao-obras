"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IconChevronDown, IconChevronRight, IconCopy, IconDots, IconRefresh } from "@tabler/icons-react";
import type { Cycle, StudyDetail } from "@/types/pre-planejamento";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { saveCycles, saveWbsOverrides } from "@/lib/api/pre-planejamento-mutations";
import { computeSchedule, suggestPredecessors, type ScheduledCycle } from "@/lib/pre-planejamento/scheduler";

// Aba "Estrutura WBS": árvore de 3 níveis (Torre → Serviço → Pavimento)
// montada a partir de study.services/floors/cycles — não cria nem remove
// pavimento aqui (isso continua só em "Serviços e lotes", exceto "Replicar
// torre", que é a única ação de estrutura que existe nesta aba), só edita
// duração das folhas e os predecessores (sim_wbs_overrides). ID sequencial e
// código WBS são recalculados a cada render (posição na árvore, não
// armazenados) — mesmo comportamento do Task ID do MS Project.

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
  groupName?: string; // só nível 1 (torre) — usado por "Replicar torre"
  ancestorKeys: string[];
}

function buildRows(study: StudyDetail): FlatRow[] {
  const floorById = new Map(study.floors.map((f) => [f.id, f]));
  const serviceById = new Map(study.services.map((s) => [s.id, s]));

  const towerOrder: string[] = [];
  for (const floor of [...study.floors].sort((a, b) => a.orderIndex - b.orderIndex)) {
    if (!towerOrder.includes(floor.groupName)) towerOrder.push(floor.groupName);
  }

  const cyclesByTower = new Map<string, Cycle[]>();
  for (const cycle of study.cycles) {
    const floor = floorById.get(cycle.floorId);
    if (!floor) continue;
    const list = cyclesByTower.get(floor.groupName) ?? [];
    list.push(cycle);
    cyclesByTower.set(floor.groupName, list);
  }

  const rows: FlatRow[] = [];
  let nextId = 1;

  towerOrder.forEach((groupName, towerIdx) => {
    const towerCycles = cyclesByTower.get(groupName) ?? [];
    if (towerCycles.length === 0) return;

    const towerWbs = `${towerIdx + 1}`;
    const towerKey = `tower:${groupName}`;
    rows.push({
      key: towerKey,
      id: nextId++,
      wbs: towerWbs,
      level: 1,
      label: groupName,
      groupName,
      ancestorKeys: [],
    });

    const serviceIdsInTower = [...new Set(towerCycles.map((c) => c.serviceId))].sort(
      (a, b) => (serviceById.get(a)?.orderIndex ?? 0) - (serviceById.get(b)?.orderIndex ?? 0),
    );

    serviceIdsInTower.forEach((serviceId, serviceIdx) => {
      const service = serviceById.get(serviceId);
      const serviceWbs = `${towerWbs}.${serviceIdx + 1}`;
      const serviceKey = `service:${groupName}:${serviceId}`;
      rows.push({
        key: serviceKey,
        id: nextId++,
        wbs: serviceWbs,
        level: 2,
        label: service?.name ?? "—",
        ancestorKeys: [towerKey],
      });

      const cyclesForService = towerCycles
        .filter((c) => c.serviceId === serviceId)
        .sort((a, b) => (floorById.get(a.floorId)?.orderIndex ?? 0) - (floorById.get(b.floorId)?.orderIndex ?? 0));

      cyclesForService.forEach((cycle, floorIdx) => {
        const floor = floorById.get(cycle.floorId);
        rows.push({
          key: `cycle:${cycle.id}`,
          id: nextId++,
          wbs: `${serviceWbs}.${floorIdx + 1}`,
          level: 3,
          label: floor?.floorName ?? "—",
          cycleId: cycle.id,
          ancestorKeys: [towerKey, serviceKey],
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

function predecessorsToText(cycleId: string, predecessors: Record<string, string[]>, rowByCycleId: Map<string, FlatRow>): string {
  return (predecessors[cycleId] ?? [])
    .map((id) => rowByCycleId.get(id)?.id)
    .filter((id): id is number => id !== undefined)
    .sort((a, b) => a - b)
    .join(";");
}

interface DragFillState {
  col: "duration" | "predecessors";
  sourceRowIndex: number;
  sourceValue: string;
  currentRowIndex: number;
}

export function WbsTable() {
  const router = useRouter();
  const { projectId, study } = useStudy();

  const [durations, setDurations] = useState<Record<string, number>>({});
  const [predecessors, setPredecessors] = useState<Record<string, string[]>>({});
  const [predecessorsText, setPredecessorsText] = useState<Record<string, string>>({});
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmGenerate, setConfirmGenerate] = useState(false);
  const [replicatingTower, setReplicatingTower] = useState<string | null>(null);
  const [openTowerMenu, setOpenTowerMenu] = useState<string | null>(null);
  const [dragFill, setDragFill] = useState<DragFillState | null>(null);

  // Ressincroniza o estado local sempre que `study` mudar (ex.: depois de um
  // router.refresh() disparado por outro save) — sem isso, os mapas de
  // duração/predecessores ficavam "presos" nos valores de quando o
  // componente montou pela primeira vez, e ciclos novos (ex.: de "Replicar
  // torre") apareciam com os campos vazios mesmo já tendo dado salvo.
  useEffect(() => {
    setDurations(Object.fromEntries(study.cycles.map((c) => [c.id, c.durationDays])));
    const map: Record<string, string[]> = {};
    for (const link of study.predecessors) {
      const list = map[link.cycleId] ?? [];
      list.push(link.predecessorId);
      map[link.cycleId] = list;
    }
    setPredecessors(map);
  }, [study]);

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

  // Sincroniza o texto exibido de predecessores sempre que os IDs (que
  // mudam de posição a cada render, dependendo da árvore) ou os dados
  // resolvidos mudarem — o campo é controlado pra "Ctrl+D"/drag fill
  // conseguirem atualizar o texto na hora, sem esperar um blur.
  useEffect(() => {
    const next: Record<string, string> = {};
    for (const row of rows) {
      if (row.cycleId) next[row.cycleId] = predecessorsToText(row.cycleId, predecessors, rowByCycleId);
    }
    setPredecessorsText(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, predecessors]);

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

  function resolvePredecessorsText(cycleId: string, text: string): string[] {
    return text
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => rowById.get(Number(s))?.cycleId)
      .filter((id): id is string => Boolean(id) && id !== cycleId);
  }

  function handlePredecessorsTextChange(cycleId: string, value: string) {
    setPredecessorsText((prev) => ({ ...prev, [cycleId]: value }));
  }

  function commitPredecessorsText(cycleId: string, value: string) {
    setPredecessors((prev) => ({ ...prev, [cycleId]: resolvePredecessorsText(cycleId, value) }));
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

  // "Replicar torre": duplica os pavimentos + ciclos da torre (nome + " (cópia)")
  // e remapeia só os predecessores INTERNOS à torre pros ciclos novos — os que
  // apontam pra fora ficam de fora da cópia (o planejador ajusta depois).
  async function replicateTower(groupName: string) {
    setOpenTowerMenu(null);
    setReplicatingTower(groupName);
    setError(null);
    try {
      const towerFloors = [...study.floors]
        .filter((f) => f.groupName === groupName)
        .sort((a, b) => a.orderIndex - b.orderIndex);
      const towerFloorIds = new Set(towerFloors.map((f) => f.id));
      const newGroupName = `${groupName} (cópia)`;

      const servicesPayload = study.services.map((s) => ({
        id: s.id,
        name: s.name,
        color: s.color,
        orderIndex: s.orderIndex,
        lagDays: s.lagDays,
      }));
      const existingFloorsPayload = study.floors.map((f) => ({
        id: f.id,
        groupName: f.groupName,
        floorName: f.floorName,
        orderIndex: f.orderIndex,
      }));
      const newFloorsPayload = towerFloors.map((f, i) => ({
        groupName: newGroupName,
        floorName: f.floorName,
        orderIndex: existingFloorsPayload.length + i,
      }));
      const floorsPayload = [...existingFloorsPayload, ...newFloorsPayload];

      const serviceIndexById = new Map(study.services.map((s, i) => [s.id, i]));
      const floorIndexById = new Map(existingFloorsPayload.map((f, i) => [f.id as string, i]));
      const newFloorIndexByOriginalFloorId = new Map<string, number>();
      towerFloors.forEach((f, i) => newFloorIndexByOriginalFloorId.set(f.id, existingFloorsPayload.length + i));

      const existingCyclesPayload = study.cycles.map((c) => ({
        serviceIndex: serviceIndexById.get(c.serviceId)!,
        floorIndex: floorIndexById.get(c.floorId)!,
        durationDays: durations[c.id] ?? c.durationDays,
      }));

      const towerCycles = study.cycles.filter((c) => towerFloorIds.has(c.floorId));
      const newCyclesPayload = towerCycles.map((c) => ({
        serviceIndex: serviceIndexById.get(c.serviceId)!,
        floorIndex: newFloorIndexByOriginalFloorId.get(c.floorId)!,
        durationDays: durations[c.id] ?? c.durationDays,
      }));

      const updatedStudy = await saveCycles(projectId, study.id, {
        services: servicesPayload,
        floors: floorsPayload,
        cycles: [...existingCyclesPayload, ...newCyclesPayload],
      });

      // Resolve os ids reais dos ciclos novos por (serviceId, floorId novo).
      const newFloorIdByFloorName = new Map(
        updatedStudy.floors.filter((f) => f.groupName === newGroupName).map((f) => [f.floorName, f.id]),
      );
      const newCycleIdByServiceAndFloor = new Map(
        updatedStudy.cycles.map((c) => [`${c.serviceId}:${c.floorId}`, c.id]),
      );
      const originalToNewCycleId = new Map<string, string>();
      for (const cycle of towerCycles) {
        const originalFloor = study.floors.find((f) => f.id === cycle.floorId);
        const newFloorId = originalFloor ? newFloorIdByFloorName.get(originalFloor.floorName) : undefined;
        if (!newFloorId) continue;
        const newCycleId = newCycleIdByServiceAndFloor.get(`${cycle.serviceId}:${newFloorId}`);
        if (newCycleId) originalToNewCycleId.set(cycle.id, newCycleId);
      }

      // Só remapeia predecessores onde AMBOS (tarefa e predecessora) são da torre original.
      const towerCycleIds = new Set(towerCycles.map((c) => c.id));
      const overridesMap: Record<string, string[]> = {};
      for (const [cycleId, predecessorIds] of Object.entries(predecessors)) overridesMap[cycleId] = [...predecessorIds];
      for (const link of study.predecessors) {
        if (!towerCycleIds.has(link.cycleId) || !towerCycleIds.has(link.predecessorId)) continue;
        const newCycleId = originalToNewCycleId.get(link.cycleId);
        const newPredecessorId = originalToNewCycleId.get(link.predecessorId);
        if (!newCycleId || !newPredecessorId) continue;
        const list = overridesMap[newCycleId] ?? [];
        list.push(newPredecessorId);
        overridesMap[newCycleId] = list;
      }

      await saveWbsOverrides(projectId, study.id, {
        overrides: Object.entries(overridesMap).map(([cycleId, predecessorIds]) => ({ cycleId, predecessorIds })),
      });

      router.refresh();
    } catch {
      setError("Não foi possível replicar a torre. Tente novamente.");
    } finally {
      setReplicatingTower(null);
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
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
      e.preventDefault();
      const aboveRow = visibleRows[rowIndex - 1];
      const currentRow = visibleRows[rowIndex];
      if (!aboveRow?.cycleId || !currentRow?.cycleId) return;
      if (col === "duration") {
        handleDurationChange(currentRow.cycleId, String(durations[aboveRow.cycleId] ?? ""));
      } else {
        const text = predecessorsText[aboveRow.cycleId] ?? "";
        handlePredecessorsTextChange(currentRow.cycleId, text);
        commitPredecessorsText(currentRow.cycleId, text);
      }
      return;
    }
    if (e.key === "Enter" || e.key === "ArrowDown") {
      e.preventDefault();
      focusCell(rowIndex + 1, col);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusCell(rowIndex - 1, col);
    }
  }

  function startDragFill(rowIndex: number, col: "duration" | "predecessors", value: string) {
    setDragFill({ col, sourceRowIndex: rowIndex, sourceValue: value, currentRowIndex: rowIndex });
  }

  useEffect(() => {
    if (!dragFill) return;
    function handleMouseUp() {
      setDragFill((current) => {
        if (!current) return null;
        const [start, end] =
          current.sourceRowIndex <= current.currentRowIndex
            ? [current.sourceRowIndex, current.currentRowIndex]
            : [current.currentRowIndex, current.sourceRowIndex];
        for (let i = start; i <= end; i++) {
          if (i === current.sourceRowIndex) continue;
          const row = visibleRows[i];
          if (!row?.cycleId) continue;
          if (current.col === "duration") handleDurationChange(row.cycleId, current.sourceValue);
          else {
            handlePredecessorsTextChange(row.cycleId, current.sourceValue);
            commitPredecessorsText(row.cycleId, current.sourceValue);
          }
        }
        return null;
      });
    }
    window.addEventListener("mouseup", handleMouseUp);
    return () => window.removeEventListener("mouseup", handleMouseUp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragFill, visibleRows]);

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
          Predecessores por ID separados por ; (ex.: 5;3) · Tab / Enter / setas navegam · Ctrl+D repete a linha
          acima · arraste o cantinho da célula pra preencher em sequência
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
                      {row.level === 1 && row.groupName && (
                        <div
                          className="relative ml-1"
                          onBlur={(e) => {
                            if (!e.currentTarget.contains(e.relatedTarget)) setOpenTowerMenu(null);
                          }}
                        >
                          <button
                            type="button"
                            disabled={replicatingTower === row.groupName}
                            onClick={() => setOpenTowerMenu(openTowerMenu === row.groupName ? null : row.groupName!)}
                            className="flex h-6 w-6 items-center justify-center rounded text-black/40 hover:bg-black/10 hover:text-black disabled:opacity-50"
                          >
                            <IconDots size={14} />
                          </button>
                          {openTowerMenu === row.groupName && (
                            <div className="absolute left-0 top-full z-20 mt-1 w-40 rounded-md border border-black/10 bg-white py-1 font-normal shadow-lg">
                              <button
                                type="button"
                                onClick={() => replicateTower(row.groupName!)}
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-black hover:bg-black/5"
                              >
                                <IconCopy size={14} /> Replicar torre
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                      {replicatingTower === row.groupName && (
                        <span className="text-xs font-normal text-black/40">replicando...</span>
                      )}
                    </div>
                  </td>
                  <td className="relative px-2 py-1.5">
                    {row.cycleId ? (
                      <>
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
                        <span
                          onMouseDown={(e) => {
                            e.preventDefault();
                            startDragFill(rowIndex, "duration", String(durations[row.cycleId as string] ?? ""));
                          }}
                          onMouseEnter={() =>
                            dragFill?.col === "duration" && setDragFill((prev) => (prev ? { ...prev, currentRowIndex: rowIndex } : prev))
                          }
                          className="absolute bottom-1 right-1 h-2 w-2 cursor-crosshair rounded-sm bg-pmon-yellow"
                          title="Arrastar pra preencher"
                        />
                      </>
                    ) : (
                      <span className="text-black/30">—</span>
                    )}
                  </td>
                  <td className="relative px-2 py-1.5">
                    {row.cycleId ? (
                      <>
                        <input
                          type="text"
                          data-row={rowIndex}
                          data-col="predecessors"
                          value={predecessorsText[row.cycleId] ?? ""}
                          onChange={(e) => handlePredecessorsTextChange(row.cycleId as string, e.target.value)}
                          onBlur={(e) => commitPredecessorsText(row.cycleId as string, e.target.value)}
                          onKeyDown={(e) => handleKeyDown(e, rowIndex, "predecessors")}
                          className="w-20 rounded border border-black/20 px-2 py-1 text-center"
                        />
                        <span
                          onMouseDown={(e) => {
                            e.preventDefault();
                            startDragFill(rowIndex, "predecessors", predecessorsText[row.cycleId as string] ?? "");
                          }}
                          onMouseEnter={() =>
                            dragFill?.col === "predecessors" &&
                            setDragFill((prev) => (prev ? { ...prev, currentRowIndex: rowIndex } : prev))
                          }
                          className="absolute bottom-1 right-1 h-2 w-2 cursor-crosshair rounded-sm bg-pmon-yellow"
                          title="Arrastar pra preencher"
                        />
                      </>
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
