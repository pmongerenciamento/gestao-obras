import type { StudyDetail } from "@/types/pre-planejamento";

// Calcula as datas de início/fim de cada ciclo pra desenhar a Linha de
// Balanço (aba só-leitura) e a aba Estrutura WBS — nenhum endpoint devolve
// isso pronto, o backend só grava dados brutos (services/floors/cycles/
// holidays/predecessors), quem calcula é o cliente.
//
// A partir da Estrutura WBS, o encadeamento é um grafo explícito de
// predecessores (editado pelo planejador, ver sim_wbs_overrides) — não mais
// a ordem implícita de pavimento. Forward-pass topológico (Kahn): tarefa sem
// predecessor começa em study.startDate; com predecessores, começa no
// próximo dia útil após o maior fim entre eles (finish-to-start, lag 0 —
// sem tipo/lag por enquanto). Ciclo no grafo de predecessores (referência
// circular) não trava: o nó envolvido cai no caso "sem predecessor válido
// ainda calculado", só perde a dependência daquele predecessor específico.

export interface ScheduledCycle {
  cycleId: string;
  start: Date;
  end: Date;
}

export interface SuggestedPredecessor {
  cycleId: string;
  predecessorId: string;
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
  const studyStart = nextWorkdayOnOrAfter(parseISODate(study.startDate), holidays);
  const cycleById = new Map(study.cycles.map((c) => [c.id, c]));

  const predecessorsByCycle = new Map<string, string[]>();
  for (const link of study.predecessors) {
    if (!cycleById.has(link.predecessorId)) continue;
    const list = predecessorsByCycle.get(link.cycleId) ?? [];
    list.push(link.predecessorId);
    predecessorsByCycle.set(link.cycleId, list);
  }

  // Ordenação topológica (Kahn) — define em que ordem processar os ciclos
  // pra sempre ter os predecessores já calculados quando chegar a vez de um nó.
  const successorsOf = new Map<string, string[]>();
  const remainingInDegree = new Map<string, number>();
  for (const cycle of study.cycles) remainingInDegree.set(cycle.id, 0);
  for (const [cycleId, preds] of predecessorsByCycle) {
    remainingInDegree.set(cycleId, preds.length);
    for (const predecessorId of preds) {
      const list = successorsOf.get(predecessorId) ?? [];
      list.push(cycleId);
      successorsOf.set(predecessorId, list);
    }
  }

  const queue: string[] = [];
  for (const [cycleId, degree] of remainingInDegree) if (degree === 0) queue.push(cycleId);

  const order: string[] = [];
  while (queue.length > 0) {
    const cycleId = queue.shift()!;
    order.push(cycleId);
    for (const successorId of successorsOf.get(cycleId) ?? []) {
      const degree = (remainingInDegree.get(successorId) ?? 0) - 1;
      remainingInDegree.set(successorId, degree);
      if (degree === 0) queue.push(successorId);
    }
  }
  // Nós que sobraram fazem parte de uma referência circular — processa por
  // último, como se não tivessem predecessor válido ainda calculado.
  const visited = new Set(order);
  for (const cycle of study.cycles) if (!visited.has(cycle.id)) order.push(cycle.id);

  const result = new Map<string, ScheduledCycle>();
  for (const cycleId of order) {
    const cycle = cycleById.get(cycleId);
    if (!cycle) continue;
    const validPredecessorEnds = (predecessorsByCycle.get(cycleId) ?? [])
      .map((predecessorId) => result.get(predecessorId))
      .filter((scheduled): scheduled is ScheduledCycle => scheduled !== undefined);

    const start =
      validPredecessorEnds.length === 0
        ? studyStart
        : addWorkdays(
            new Date(Math.max(...validPredecessorEnds.map((s) => s.end.getTime()))),
            1,
            holidays,
          );
    const end = addWorkdays(start, cycle.durationDays - 1, holidays);
    result.set(cycleId, { cycleId, start, end });
  }

  return result;
}

/** Sugestão de predecessores pro botão "Gerar estrutura automática": encadeia,
 * pra cada serviço dentro de cada grupo/torre, os pavimentos consecutivos
 * (por orderIndex) que têm ciclo daquele serviço — mesma lógica que já foi o
 * cálculo automático de datas antes da Estrutura WBS existir, agora só como
 * ponto de partida editável, não mais aplicada automaticamente.
 */
export function suggestPredecessors(study: StudyDetail): SuggestedPredecessor[] {
  const floorById = new Map(study.floors.map((f) => [f.id, f]));
  const chains = new Map<string, typeof study.cycles>();
  for (const cycle of study.cycles) {
    const floor = floorById.get(cycle.floorId);
    if (!floor) continue;
    const key = `${cycle.serviceId}::${floor.groupName}`;
    const list = chains.get(key) ?? [];
    list.push(cycle);
    chains.set(key, list);
  }

  const suggestions: SuggestedPredecessor[] = [];
  for (const chainCycles of chains.values()) {
    const ordered = [...chainCycles].sort(
      (a, b) => (floorById.get(a.floorId)?.orderIndex ?? 0) - (floorById.get(b.floorId)?.orderIndex ?? 0),
    );
    for (let i = 1; i < ordered.length; i++) {
      suggestions.push({ cycleId: ordered[i].id, predecessorId: ordered[i - 1].id });
    }
  }
  return suggestions;
}

export { isWorkday, toISODate, parseISODate };
