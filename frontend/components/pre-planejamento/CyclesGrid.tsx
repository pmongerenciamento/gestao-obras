"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IconCopy, IconPlus, IconTrash, IconX } from "@tabler/icons-react";
import type { FloorInput, ServiceInput } from "@/types/pre-planejamento";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { saveCycles } from "@/lib/api/pre-planejamento-mutations";

// Aba "Serviços e lotes": tabela estilo planilha (grupo/torre com label
// vertical + pavimento sticky à esquerda, serviços roláveis horizontalmente).
// Estado local até clicar "Salvar" — não salva a cada tecla.
//
// service.lagDays fica sempre 0 por enquanto: a defasagem entre pavimentos
// vai ser controlada pela aba de estrutura WBS (predecessoras/sucessoras),
// ainda não implementada — o campo continua existindo em sim_services (não
// precisa de migration pra reverter isso depois), só não tem mais UI nem
// entra no cálculo de lib/pre-planejamento/scheduler.ts.

const GROUP_COLORS = ["#E07A3F", "#3F7BE0", "#5FA85A", "#B15FD9", "#D9527A"];

function cycleKey(serviceIndex: number, floorIndex: number) {
  return `${serviceIndex}:${floorIndex}`;
}

function sanitizeDigits(value: string): string {
  return value.replace(/\D/g, "");
}

// Remove pavimentos por índice e reindexa as chaves de `cycles` (o índice de
// pavimento faz parte da chave, então remover um do meio do array precisa
// deslocar as chaves dos que vinham depois — sem isso a duração salva passa
// a apontar pro pavimento errado após a remoção).
function removeFloorsAndRemapCycles(
  floors: FloorInput[],
  cycles: Record<string, number>,
  removedIndices: Set<number>,
): { floors: FloorInput[]; cycles: Record<string, number> } {
  const indexMap = new Map<number, number>();
  const newFloors: FloorInput[] = [];
  floors.forEach((floor, oldIndex) => {
    if (removedIndices.has(oldIndex)) return;
    indexMap.set(oldIndex, newFloors.length);
    newFloors.push(floor);
  });

  const newCycles: Record<string, number> = {};
  for (const [key, duration] of Object.entries(cycles)) {
    const [serviceIndex, floorIndex] = key.split(":").map(Number);
    const newFloorIndex = indexMap.get(floorIndex);
    if (newFloorIndex !== undefined) newCycles[cycleKey(serviceIndex, newFloorIndex)] = duration;
  }
  return { floors: newFloors, cycles: newCycles };
}

// Mesmo problema de reindexação, só que pro índice de serviço.
function removeServiceAndRemapCycles(
  services: ServiceInput[],
  cycles: Record<string, number>,
  removedIndex: number,
): { services: ServiceInput[]; cycles: Record<string, number> } {
  const newServices = services.filter((_, i) => i !== removedIndex);
  const newCycles: Record<string, number> = {};
  for (const [key, duration] of Object.entries(cycles)) {
    const [serviceIndex, floorIndex] = key.split(":").map(Number);
    if (serviceIndex === removedIndex) continue;
    const newServiceIndex = serviceIndex > removedIndex ? serviceIndex - 1 : serviceIndex;
    newCycles[cycleKey(newServiceIndex, floorIndex)] = duration;
  }
  return { services: newServices, cycles: newCycles };
}

// Cor automática por serviço via golden angle (137.5°) — maximiza a
// distinção entre matizes adjacentes mesmo com muitos serviços (~50),
// diferente da paleta fixa (curta) usada pros grupos/torres.
function generateServiceColor(index: number): string {
  const hue = (index * 137.5) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

export function CyclesGrid() {
  const router = useRouter();
  const { projectId, study } = useStudy();

  const [groups, setGroups] = useState<string[]>(() => [
    ...new Set(study.floors.map((f) => f.groupName)),
  ]);
  const [services, setServices] = useState<ServiceInput[]>(() =>
    [...study.services]
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((s) => ({ id: s.id, name: s.name, color: s.color, orderIndex: s.orderIndex, lagDays: s.lagDays })),
  );
  const [floors, setFloors] = useState<FloorInput[]>(() =>
    [...study.floors]
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((f) => ({ id: f.id, groupName: f.groupName, floorName: f.floorName, orderIndex: f.orderIndex })),
  );
  const [cycles, setCycles] = useState<Record<string, number>>(() => {
    const serviceIndexById = new Map(study.services.map((s, i) => [s.id, i]));
    const floorIndexById = new Map(study.floors.map((f, i) => [f.id, i]));
    const map: Record<string, number> = {};
    for (const cycle of study.cycles) {
      const si = serviceIndexById.get(cycle.serviceId);
      const fi = floorIndexById.get(cycle.floorId);
      if (si !== undefined && fi !== undefined) map[cycleKey(si, fi)] = cycle.durationDays;
    }
    return map;
  });
  const [defaults, setDefaults] = useState<Record<number, string>>({});

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newGroupOpen, setNewGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newFloorOpen, setNewFloorOpen] = useState(false);
  const [newFloorGroup, setNewFloorGroup] = useState("");
  const [newFloorNames, setNewFloorNames] = useState("");
  const [applyConfirmIndex, setApplyConfirmIndex] = useState<number | null>(null);
  const [deleteGroupTarget, setDeleteGroupTarget] = useState<string | null>(null);

  const floorGroups = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const group of groups) map.set(group, []);
    floors.forEach((floor, index) => {
      const list = map.get(floor.groupName) ?? [];
      list.push(index);
      map.set(floor.groupName, list);
    });
    return map;
  }, [groups, floors]);

  function updateService(index: number, patch: Partial<ServiceInput>) {
    setServices((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function removeService(index: number) {
    const { services: newServices, cycles: newCycles } = removeServiceAndRemapCycles(services, cycles, index);
    setServices(newServices);
    setCycles(newCycles);
  }

  function addService() {
    setServices((prev) => [
      ...prev,
      {
        name: `Serviço ${prev.length + 1}`,
        color: generateServiceColor(prev.length),
        orderIndex: prev.length,
        lagDays: 0,
      },
    ]);
  }

  function removeFloor(index: number) {
    const { floors: newFloors, cycles: newCycles } = removeFloorsAndRemapCycles(floors, cycles, new Set([index]));
    setFloors(newFloors);
    setCycles(newCycles);
  }

  function addGroup(name: string) {
    setGroups((prev) => (prev.includes(name) ? prev : [...prev, name]));
  }

  function removeGroup(groupName: string) {
    const removedIndices = new Set(
      floors.reduce<number[]>((acc, floor, index) => {
        if (floor.groupName === groupName) acc.push(index);
        return acc;
      }, []),
    );
    const { floors: newFloors, cycles: newCycles } = removeFloorsAndRemapCycles(floors, cycles, removedIndices);
    setFloors(newFloors);
    setCycles(newCycles);
    setGroups((prev) => prev.filter((g) => g !== groupName));
    setDeleteGroupTarget(null);
  }

  // Duplica os pavimentos + durações já preenchidas de um grupo/torre sob um
  // novo nome (sufixo " (cópia)") — puramente local, igual "+ Grupo"/"+
  // Pavimento": só vai pro banco quando o usuário clicar em "Salvar".
  function replicateGroup(groupName: string) {
    const sourceIndices = floors.reduce<number[]>((acc, floor, index) => {
      if (floor.groupName === groupName) acc.push(index);
      return acc;
    }, []);
    if (sourceIndices.length === 0) return;

    let newGroupName = `${groupName} (cópia)`;
    let suffix = 2;
    while (groups.includes(newGroupName)) {
      newGroupName = `${groupName} (cópia ${suffix})`;
      suffix += 1;
    }

    const sortedSourceIndices = [...sourceIndices].sort((a, b) => floors[a].orderIndex - floors[b].orderIndex);
    const newFloors = sortedSourceIndices.map((floorIndex, i) => ({
      groupName: newGroupName,
      floorName: floors[floorIndex].floorName,
      orderIndex: floors.length + i,
    }));

    const newCycles = { ...cycles };
    sortedSourceIndices.forEach((oldFloorIndex, i) => {
      const newFloorIndex = floors.length + i;
      services.forEach((_, serviceIndex) => {
        const key = cycleKey(serviceIndex, oldFloorIndex);
        if (key in cycles) newCycles[cycleKey(serviceIndex, newFloorIndex)] = cycles[key];
      });
    });

    setFloors([...floors, ...newFloors]);
    setCycles(newCycles);
    setGroups([...groups, newGroupName]);
  }

  function addFloors(groupName: string, rawNames: string) {
    const names = rawNames
      .split(";")
      .map((n) => n.trim())
      .filter(Boolean);
    if (names.length === 0) return;
    setFloors((prev) => [
      ...prev,
      ...names.map((floorName, i) => ({ groupName, floorName, orderIndex: prev.length + i })),
    ]);
  }

  function updateCycle(serviceIndex: number, floorIndex: number, value: string) {
    const key = cycleKey(serviceIndex, floorIndex);
    const digits = sanitizeDigits(value);
    setCycles((prev) => {
      const next = { ...prev };
      const duration = Number(digits);
      if (!digits || duration <= 0) {
        delete next[key];
      } else {
        next[key] = duration;
      }
      return next;
    });
  }

  function applyDefault(serviceIndex: number) {
    const hasExisting = floors.some((_, floorIndex) => cycleKey(serviceIndex, floorIndex) in cycles);
    if (hasExisting) {
      setApplyConfirmIndex(serviceIndex);
      return;
    }
    doApplyDefault(serviceIndex);
  }

  function doApplyDefault(serviceIndex: number) {
    const duration = Number(defaults[serviceIndex] ?? "");
    if (!duration || duration <= 0) return;
    setCycles((prev) => {
      const next = { ...prev };
      floors.forEach((_, floorIndex) => {
        next[cycleKey(serviceIndex, floorIndex)] = duration;
      });
      return next;
    });
    setApplyConfirmIndex(null);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const cycleInputs = Object.entries(cycles).map(([key, durationDays]) => {
        const [serviceIndex, floorIndex] = key.split(":").map(Number);
        return { serviceIndex, floorIndex, durationDays };
      });
      await saveCycles(projectId, study.id, {
        services: services.map((s, i) => ({ ...s, orderIndex: i })),
        floors: floors.map((f, i) => ({ ...f, orderIndex: i })),
        cycles: cycleInputs,
      });
      router.refresh();
    } catch {
      setError("Não foi possível salvar a grade. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setNewGroupOpen(true)}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15"
        >
          <IconPlus size={16} /> Grupo
        </button>
        <button
          type="button"
          onClick={() => setNewFloorOpen(true)}
          disabled={groups.length === 0}
          title={groups.length === 0 ? "Crie um grupo primeiro" : undefined}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <IconPlus size={16} /> Pavimento
        </button>
        <button
          type="button"
          onClick={addService}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15"
        >
          <IconPlus size={16} /> Serviço
        </button>
        <span className="ml-1 text-xs text-black/40">
          &quot;+ Pavimento&quot; aceita vários nomes separados por ; · navegue pelas células com Tab / Enter
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-black/10 bg-white">
        <table className="border-collapse text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-8 border-b border-r border-black/10 bg-black/[0.02]" />
              <th className="sticky left-8 z-10 min-w-[160px] border-b border-r border-black/10 bg-black/[0.02] px-3 py-2 text-left font-medium text-black/50">
                Pavimento
              </th>
              {services.map((service, serviceIndex) => (
                <th key={serviceIndex} className="min-w-[150px] border-b border-l border-black/10 px-3 py-2">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-1">
                      <span
                        className="h-4 w-4 shrink-0 rounded"
                        style={{ backgroundColor: service.color }}
                        title="Cor atribuída automaticamente"
                      />
                      <input
                        value={service.name}
                        onChange={(e) => updateService(serviceIndex, { name: e.target.value })}
                        className="w-full min-w-0 border-b border-transparent bg-transparent text-left text-sm font-medium text-black focus:border-black/30 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => removeService(serviceIndex)}
                        className="shrink-0 text-black/30 hover:text-red-600"
                      >
                        <IconTrash size={14} />
                      </button>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-normal text-black/50">
                      Padrão:
                      <input
                        type="text"
                        inputMode="numeric"
                        value={defaults[serviceIndex] ?? ""}
                        onChange={(e) => setDefaults((prev) => ({ ...prev, [serviceIndex]: sanitizeDigits(e.target.value) }))}
                        className="w-10 rounded border border-black/20 px-1 py-0.5 text-xs"
                      />
                      <button
                        type="button"
                        onClick={() => applyDefault(serviceIndex)}
                        className="rounded border border-black/20 bg-black/[0.02] px-1.5 py-0.5 text-[11px] text-black/60 hover:bg-black/10"
                      >
                        Aplicar ▾
                      </button>
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...floorGroups.entries()].map(([groupName, floorIndices], groupPosition) => (
              <FloorGroupRows
                key={groupName}
                groupName={groupName}
                groupColor={GROUP_COLORS[groupPosition % GROUP_COLORS.length]}
                floorIndices={floorIndices}
                floors={floors}
                services={services}
                cycles={cycles}
                onUpdateCycle={updateCycle}
                onRemoveFloor={removeFloor}
                onRequestRemoveGroup={setDeleteGroupTarget}
                onReplicateGroup={replicateGroup}
                columnCount={services.length}
              />
            ))}
            {groups.length === 0 && (
              <tr>
                <td colSpan={services.length + 2} className="px-4 py-8 text-center text-black/50">
                  Nenhum grupo/torre cadastrado ainda.
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

      {newGroupOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setNewGroupOpen(false)}
        >
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-black">Novo grupo/torre</h2>
            <div className="mt-4">
              <Input
                id="newGroupName"
                label="Nome do grupo/torre"
                variant="light"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
              />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setNewGroupOpen(false)}
                className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15"
              >
                Cancelar
              </button>
              <Button
                onClick={() => {
                  if (!newGroupName.trim()) return;
                  addGroup(newGroupName.trim());
                  setNewGroupName("");
                  setNewGroupOpen(false);
                }}
              >
                Adicionar
              </Button>
            </div>
          </div>
        </div>
      )}

      {newFloorOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setNewFloorOpen(false)}
        >
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-black">Novo pavimento</h2>
            <div className="mt-4 flex flex-col gap-4">
              <Select
                id="newFloorGroup"
                label="Grupo/torre"
                variant="light"
                placeholder="Selecione"
                options={groups.map((g) => ({ value: g, label: g }))}
                value={newFloorGroup}
                onChange={(e) => setNewFloorGroup(e.target.value)}
              />
              <Input
                id="newFloorNames"
                label="Pavimento(s)"
                variant="light"
                placeholder="Ex.: Térreo;1º Pav;2º Pav"
                value={newFloorNames}
                onChange={(e) => setNewFloorNames(e.target.value)}
              />
              <p className="-mt-2 text-xs text-black/40">Separe vários pavimentos por ;</p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setNewFloorOpen(false)}
                className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15"
              >
                Cancelar
              </button>
              <Button
                onClick={() => {
                  if (!newFloorGroup || !newFloorNames.trim()) return;
                  addFloors(newFloorGroup, newFloorNames);
                  setNewFloorNames("");
                  setNewFloorOpen(false);
                }}
              >
                Adicionar
              </Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={applyConfirmIndex !== null}
        title="Sobrescrever durações preenchidas?"
        description="Esse serviço já tem duração preenchida em algum pavimento. Aplicar o padrão vai sobrescrever todos os valores dessa coluna."
        confirmLabel="Sobrescrever"
        onConfirm={() => applyConfirmIndex !== null && doApplyDefault(applyConfirmIndex)}
        onCancel={() => setApplyConfirmIndex(null)}
      />

      <ConfirmDialog
        open={deleteGroupTarget !== null}
        title="Excluir grupo/torre"
        description={`Excluir "${deleteGroupTarget}" e todos os seus pavimentos? Esta ação não pode ser desfeita.`}
        confirmLabel="Excluir"
        onConfirm={() => deleteGroupTarget !== null && removeGroup(deleteGroupTarget)}
        onCancel={() => setDeleteGroupTarget(null)}
      />
    </div>
  );
}

interface FloorGroupRowsProps {
  groupName: string;
  groupColor: string;
  floorIndices: number[];
  floors: FloorInput[];
  services: ServiceInput[];
  cycles: Record<string, number>;
  onUpdateCycle: (serviceIndex: number, floorIndex: number, value: string) => void;
  onRemoveFloor: (index: number) => void;
  onRequestRemoveGroup: (groupName: string) => void;
  onReplicateGroup: (groupName: string) => void;
  columnCount: number;
}

function GroupLabelCell({
  groupName,
  groupColor,
  rowSpan,
  onRequestRemoveGroup,
  onReplicateGroup,
}: {
  groupName: string;
  groupColor: string;
  rowSpan?: number;
  onRequestRemoveGroup: (groupName: string) => void;
  onReplicateGroup: (groupName: string) => void;
}) {
  return (
    <td
      rowSpan={rowSpan}
      className="sticky left-0 z-10 w-8 border-b border-r border-black/10 text-center text-[10px] font-bold text-white"
      style={{ backgroundColor: groupColor }}
    >
      <div
        className="flex items-center justify-center gap-1 py-2"
        style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
      >
        <button
          type="button"
          onClick={() => onRequestRemoveGroup(groupName)}
          className="text-white/70 hover:text-white"
          title="Excluir grupo/torre"
        >
          <IconX size={12} />
        </button>
        <button
          type="button"
          onClick={() => onReplicateGroup(groupName)}
          className="text-white/70 hover:text-white"
          title="Replicar torre"
        >
          <IconCopy size={12} />
        </button>
        {groupName.toUpperCase()}
      </div>
    </td>
  );
}

function FloorGroupRows({
  groupName,
  groupColor,
  floorIndices,
  floors,
  services,
  cycles,
  onUpdateCycle,
  onRemoveFloor,
  onRequestRemoveGroup,
  onReplicateGroup,
  columnCount,
}: FloorGroupRowsProps) {
  if (floorIndices.length === 0) {
    return (
      <tr>
        <GroupLabelCell
          groupName={groupName}
          groupColor={groupColor}
          onRequestRemoveGroup={onRequestRemoveGroup}
          onReplicateGroup={onReplicateGroup}
        />
        <td colSpan={columnCount + 1} className="border-b border-black/10 px-3 py-3 text-sm text-black/40">
          Nenhum pavimento neste grupo ainda.
        </td>
      </tr>
    );
  }

  return (
    <>
      {floorIndices.map((floorIndex, i) => (
        <tr key={floorIndex}>
          {i === 0 && (
            <GroupLabelCell
              groupName={groupName}
              groupColor={groupColor}
              rowSpan={floorIndices.length}
              onRequestRemoveGroup={onRequestRemoveGroup}
              onReplicateGroup={onReplicateGroup}
            />
          )}
          <td className="sticky left-8 z-10 border-b border-r border-black/10 bg-white px-3 py-2 text-black">
            <div className="flex items-center justify-between gap-2">
              {floors[floorIndex].floorName}
              <button
                type="button"
                onClick={() => onRemoveFloor(floorIndex)}
                className="shrink-0 text-black/30 hover:text-red-600"
              >
                <IconTrash size={14} />
              </button>
            </div>
          </td>
          {services.map((_, serviceIndex) => (
            <td key={serviceIndex} className="border-b border-l border-black/10 px-2 py-1">
              <input
                type="text"
                inputMode="numeric"
                value={cycles[cycleKey(serviceIndex, floorIndex)] ?? ""}
                onChange={(e) => onUpdateCycle(serviceIndex, floorIndex, e.target.value)}
                className="w-16 rounded border border-black/20 px-2 py-1 text-center text-sm"
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
