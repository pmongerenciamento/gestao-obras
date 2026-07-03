import type { StudyDetail } from "@/types/pre-planejamento";

// Calcula as datas de início/fim de cada ciclo pra desenhar a Linha de
// Balanço (aba só-leitura) — nenhum endpoint devolve isso pronto, o backend
// só grava dados brutos (services/floors/cycles/holidays), quem calcula é o
// cliente. Pra cada serviço, dentro de cada grupo/torre, encadeia os
// pavimentos (por orderIndex) que têm ciclo daquele serviço — grupos
// diferentes têm sequências independentes, todas começando em
// study.startDate (decisões do usuário, ver plano da sessão). duration_days
// conta em dias úteis (pula fim de semana e feriados do estudo).

export interface ScheduledCycle {
  cycleId: string;
  start: Date;
  end: Date;
}

function toISODate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function isWorkday(date: Date, holidays: Set<string>): boolean {
  const day = date.getDay();
  if (day === 0 || day === 6) return false;
  return !holidays.has(toISODate(date));
}

function nextWorkdayOnOrAfter(date: Date, holidays: Set<string>): Date {
  const result = new Date(date);
  while (!isWorkday(result, holidays)) {
    result.setDate(result.getDate() + 1);
  }
  return result;
}

/** Avança `n` dias úteis a partir de `date` (não conta o próprio `date`). */
function addWorkdays(date: Date, n: number, holidays: Set<string>): Date {
  const result = new Date(date);
  let remaining = n;
  while (remaining > 0) {
    result.setDate(result.getDate() + 1);
    if (isWorkday(result, holidays)) remaining--;
  }
  return result;
}

export function computeSchedule(study: StudyDetail): Map<string, ScheduledCycle> {
  const holidays = new Set(study.holidays.map((h) => h.date));
  const floorById = new Map(study.floors.map((f) => [f.id, f]));
  const serviceById = new Map(study.services.map((s) => [s.id, s]));
  const studyStart = nextWorkdayOnOrAfter(parseISODate(study.startDate), holidays);

  const chains = new Map<string, typeof study.cycles>();
  for (const cycle of study.cycles) {
    const floor = floorById.get(cycle.floorId);
    if (!floor) continue;
    const key = `${cycle.serviceId}::${floor.groupName}`;
    const list = chains.get(key) ?? [];
    list.push(cycle);
    chains.set(key, list);
  }

  const result = new Map<string, ScheduledCycle>();

  for (const [key, chainCycles] of chains) {
    const serviceId = key.split("::")[0];
    const lagDays = serviceById.get(serviceId)?.lagDays ?? 0;

    const ordered = [...chainCycles].sort(
      (a, b) => (floorById.get(a.floorId)?.orderIndex ?? 0) - (floorById.get(b.floorId)?.orderIndex ?? 0),
    );

    let previousEnd: Date | null = null;
    for (const cycle of ordered) {
      const start = previousEnd ? addWorkdays(previousEnd, lagDays + 1, holidays) : studyStart;
      const end = addWorkdays(start, cycle.durationDays - 1, holidays);
      result.set(cycle.id, { cycleId: cycle.id, start, end });
      previousEnd = end;
    }
  }

  return result;
}

export { isWorkday, toISODate, parseISODate };
