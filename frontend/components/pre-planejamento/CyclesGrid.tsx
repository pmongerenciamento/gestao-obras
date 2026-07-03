"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import type { FloorInput, ServiceInput } from "@/types/pre-planejamento";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { saveCycles } from "@/lib/api/pre-planejamento-mutations";

// Aba "Serviços e lotes": tabela estilo planilha (pavimento sticky à
// esquerda, serviços roláveis horizontalmente). Estado local até clicar
// "Salvar" — não salva a cada tecla. service.lagDays é a defasagem (dias)
// entre pavimentos consecutivos do mesmo serviço dentro do mesmo grupo/torre
// (decisão do usuário, ver plano da sessão) — o backend encadeia
// automaticamente com base nisso ao salvar.

function cycleKey(serviceIndex: number, floorIndex: number) {
  return `${serviceIndex}:${floorIndex}`;
}

export function CyclesGrid() {
  const router = useRouter();
  const { projectId, study } = useStudy();

  const [services, setServices] = useState<ServiceInput[]>(() =>
    [...study.services]
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((s) => ({ name: s.name, color: s.color, orderIndex: s.orderIndex, lagDays: s.lagDays })),
  );
  const [floors, setFloors] = useState<FloorInput[]>(() =>
    [...study.floors]
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((f) => ({ groupName: f.groupName, floorName: f.floorName, orderIndex: f.orderIndex })),
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

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newFloorOpen, setNewFloorOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newFloorName, setNewFloorName] = useState("");

  const floorGroups = useMemo(() => {
    const groups = new Map<string, number[]>();
    floors.forEach((floor, index) => {
      const list = groups.get(floor.groupName) ?? [];
      list.push(index);
      groups.set(floor.groupName, list);
    });
    return groups;
  }, [floors]);

  function updateService(index: number, patch: Partial<ServiceInput>) {
    setServices((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function removeService(index: number) {
    setServices((prev) => prev.filter((_, i) => i !== index));
    setCycles((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        const [si] = key.split(":").map(Number);
        if (si === index) delete next[key];
      }
      return next;
    });
  }

  function addService() {
    setServices((prev) => [
      ...prev,
      { name: `Serviço ${prev.length + 1}`, color: "#F5C400", orderIndex: prev.length, lagDays: 0 },
    ]);
  }

  function removeFloor(index: number) {
    setFloors((prev) => prev.filter((_, i) => i !== index));
    setCycles((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        const [, fi] = key.split(":").map(Number);
        if (fi === index) delete next[key];
      }
      return next;
    });
  }

  function addFloor(groupName: string, floorName: string) {
    setFloors((prev) => [...prev, { groupName, floorName, orderIndex: prev.length }]);
  }

  function updateCycle(serviceIndex: number, floorIndex: number, value: string) {
    const key = cycleKey(serviceIndex, floorIndex);
    setCycles((prev) => {
      const next = { ...prev };
      const duration = Number(value);
      if (!value || duration <= 0) {
        delete next[key];
      } else {
        next[key] = duration;
      }
      return next;
    });
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
      <div className="flex gap-2">
        <button
          type="button"
          onClick={addService}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15"
        >
          <IconPlus size={16} /> Serviço
        </button>
        <button
          type="button"
          onClick={() => setNewFloorOpen(true)}
          className="flex items-center gap-1 rounded-md bg-black/10 px-3 py-2 text-sm font-medium text-black hover:bg-black/15"
        >
          <IconPlus size={16} /> Pavimento
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-black/10 bg-white">
        <table className="border-collapse text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 min-w-[160px] border-b border-r border-black/10 bg-black/[0.02] px-3 py-2 text-left font-medium text-black/50">
                Pavimento
              </th>
              {services.map((service, serviceIndex) => (
                <th key={serviceIndex} className="min-w-[140px] border-b border-l border-black/10 px-3 py-2">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-1">
                      <input
                        type="color"
                        value={service.color}
                        onChange={(e) => updateService(serviceIndex, { color: e.target.value })}
                        className="h-5 w-5 shrink-0 cursor-pointer border-0 p-0"
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
                    <label className="flex items-center gap-1 text-xs font-normal text-black/50">
                      Defasagem
                      <input
                        type="number"
                        min={0}
                        value={service.lagDays}
                        onChange={(e) => updateService(serviceIndex, { lagDays: Number(e.target.value) || 0 })}
                        className="w-12 rounded border border-black/20 px-1 py-0.5 text-xs"
                      />
                    </label>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...floorGroups.entries()].map(([groupName, floorIndices]) => (
              <FloorGroupRows
                key={groupName}
                groupName={groupName}
                floorIndices={floorIndices}
                floors={floors}
                services={services}
                cycles={cycles}
                onUpdateCycle={updateCycle}
                onRemoveFloor={removeFloor}
                columnCount={services.length}
              />
            ))}
            {floors.length === 0 && (
              <tr>
                <td colSpan={services.length + 1} className="px-4 py-8 text-center text-black/50">
                  Nenhum pavimento cadastrado.
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

      {newFloorOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setNewFloorOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-black">Novo pavimento</h2>
            <div className="mt-4 flex flex-col gap-4">
              <Input
                id="newGroupName"
                label="Grupo/torre"
                variant="light"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
              />
              <Input
                id="newFloorName"
                label="Pavimento"
                variant="light"
                value={newFloorName}
                onChange={(e) => setNewFloorName(e.target.value)}
              />
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
                  if (!newGroupName.trim() || !newFloorName.trim()) return;
                  addFloor(newGroupName.trim(), newFloorName.trim());
                  setNewGroupName("");
                  setNewFloorName("");
                  setNewFloorOpen(false);
                }}
              >
                Adicionar
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface FloorGroupRowsProps {
  groupName: string;
  floorIndices: number[];
  floors: FloorInput[];
  services: ServiceInput[];
  cycles: Record<string, number>;
  onUpdateCycle: (serviceIndex: number, floorIndex: number, value: string) => void;
  onRemoveFloor: (index: number) => void;
  columnCount: number;
}

function FloorGroupRows({
  groupName,
  floorIndices,
  floors,
  services,
  cycles,
  onUpdateCycle,
  onRemoveFloor,
  columnCount,
}: FloorGroupRowsProps) {
  return (
    <>
      <tr>
        <td
          colSpan={columnCount + 1}
          className="sticky left-0 border-b border-black/10 bg-pmon-yellow/10 px-3 py-1 text-xs font-semibold text-black/70"
        >
          {groupName}
        </td>
      </tr>
      {floorIndices.map((floorIndex) => (
        <tr key={floorIndex}>
          <td className="sticky left-0 z-10 border-b border-r border-black/10 bg-white px-3 py-2 text-black">
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
                type="number"
                min={0}
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
