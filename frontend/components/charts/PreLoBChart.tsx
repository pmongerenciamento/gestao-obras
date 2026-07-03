"use client";

import { useMemo } from "react";
import { scaleBand, timeDay } from "d3";
import { useStudy } from "@/components/pre-planejamento/StudyContext";
import { computeSchedule, toISODate } from "@/lib/pre-planejamento/scheduler";

// Aba "Linha de balanço" — só visualização (MVP, sem clique-para-editar).
// D3 usado pro cálculo de posição (scaleBand sobre o índice do dia, timeDay
// pra montar o intervalo de datas) — a renderização em si é HTML/React, não
// SVG imperativo, pra integrar limpo com o resto do app.

const DAY_WIDTH = 28;
const ROW_HEIGHT = 32;
const WEEKDAY_LETTERS = ["D", "S", "T", "Q", "Q", "S", "S"];

interface FloorTrack {
  cycleId: string;
  serviceId: string;
  start: Date;
  end: Date;
}

/** Interval partitioning: só cria sub-linha nova quando há sobreposição de horário. */
function partitionIntoTracks(items: FloorTrack[]): FloorTrack[][] {
  const sorted = [...items].sort((a, b) => a.start.getTime() - b.start.getTime());
  const tracks: FloorTrack[][] = [];

  for (const item of sorted) {
    const track = tracks.find((t) => t[t.length - 1].end.getTime() < item.start.getTime());
    if (track) {
      track.push(item);
    } else {
      tracks.push([item]);
    }
  }
  return tracks;
}

export function PreLoBChart() {
  const { study } = useStudy();

  const schedule = useMemo(() => computeSchedule(study), [study]);

  const { days, rangeStart } = useMemo(() => {
    if (schedule.size === 0) return { days: [] as Date[], rangeStart: null as Date | null };
    const starts = [...schedule.values()].map((s) => s.start.getTime());
    const ends = [...schedule.values()].map((s) => s.end.getTime());
    const min = new Date(Math.min(...starts));
    const max = new Date(Math.max(...ends));
    return { days: timeDay.range(min, timeDay.offset(max, 1)), rangeStart: min };
  }, [schedule]);

  const xScale = useMemo(
    () =>
      scaleBand<number>()
        .domain(days.map((_, i) => i))
        .range([0, days.length * DAY_WIDTH]),
    [days],
  );

  const holidaySet = useMemo(() => new Set(study.holidays.map((h) => h.date)), [study.holidays]);
  const serviceById = useMemo(() => new Map(study.services.map((s) => [s.id, s])), [study.services]);
  const floorsByGroup = useMemo(() => {
    const groups = new Map<string, typeof study.floors>();
    for (const floor of [...study.floors].sort((a, b) => a.orderIndex - b.orderIndex)) {
      const list = groups.get(floor.groupName) ?? [];
      list.push(floor);
      groups.set(floor.groupName, list);
    }
    return groups;
  }, [study]);

  const cyclesByFloor = useMemo(() => {
    const map = new Map<string, FloorTrack[]>();
    for (const cycle of study.cycles) {
      const scheduled = schedule.get(cycle.id);
      if (!scheduled) continue;
      const list = map.get(cycle.floorId) ?? [];
      list.push({ cycleId: cycle.id, serviceId: cycle.serviceId, start: scheduled.start, end: scheduled.end });
      map.set(cycle.floorId, list);
    }
    return map;
  }, [study.cycles, schedule]);

  if (days.length === 0 || !rangeStart) {
    return (
      <p className="text-sm text-black/50">
        Nenhum ciclo cadastrado ainda — preencha a aba &quot;Serviços e lotes&quot; pra ver a linha de balanço.
      </p>
    );
  }

  const dayIndex = (date: Date) => Math.round((date.getTime() - rangeStart.getTime()) / 86_400_000);
  const barLeft = (start: Date) => xScale(dayIndex(start))!;
  const barWidth = (start: Date, end: Date) => (dayIndex(end) - dayIndex(start) + 1) * DAY_WIDTH;
  const totalWidth = days.length * DAY_WIDTH;

  const months: { label: string; width: number }[] = [];
  const weeks: { label: string; width: number }[] = [];
  days.forEach((day) => {
    const monthLabel = day.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
    const last = months[months.length - 1];
    if (last && last.label === monthLabel) last.width += DAY_WIDTH;
    else months.push({ label: monthLabel, width: DAY_WIDTH });

    const daysSinceMonday = (day.getDay() + 6) % 7;
    const weekStart = new Date(day);
    weekStart.setDate(day.getDate() - daysSinceMonday);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 6);
    const weekLabel = `${weekStart.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} - ${weekEnd.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`;
    const lastWeek = weeks[weeks.length - 1];
    if (lastWeek && lastWeek.label === weekLabel) lastWeek.width += DAY_WIDTH;
    else weeks.push({ label: weekLabel, width: DAY_WIDTH });
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-black/10 bg-white">
      <div style={{ width: totalWidth + 160 }}>
        {/* Cabeçalho: 3 níveis (mês / semana / letra do dia) */}
        <div className="sticky top-0 z-10 flex border-b border-black/10 bg-white">
          <div className="sticky left-0 z-20 w-[160px] shrink-0 border-r border-black/10 bg-black/[0.02]" />
          <div className="flex flex-col">
            <div className="flex border-b border-black/10">
              {months.map((m, i) => (
                <div
                  key={i}
                  style={{ width: m.width }}
                  className="shrink-0 border-r border-black/10 px-1 py-1 text-center text-xs font-medium capitalize text-black/70"
                >
                  {m.label}
                </div>
              ))}
            </div>
            <div className="flex border-b border-black/10">
              {weeks.map((w, i) => (
                <div
                  key={i}
                  style={{ width: w.width }}
                  className="shrink-0 border-r border-black/10 px-1 py-1 text-center text-[10px] text-black/50"
                >
                  {w.label}
                </div>
              ))}
            </div>
            <div className="flex">
              {days.map((day, i) => {
                const isGray = day.getDay() === 0 || day.getDay() === 6 || holidaySet.has(toISODate(day));
                return (
                  <div
                    key={i}
                    style={{ width: DAY_WIDTH }}
                    className={`shrink-0 border-r border-black/5 py-1 text-center text-xs ${
                      isGray ? "bg-black/10 text-black/40" : "text-black/60"
                    }`}
                  >
                    {WEEKDAY_LETTERS[day.getDay()]}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Fundo cinza de fim de semana/feriado atrás das linhas */}
        <div className="relative">
          <div className="pointer-events-none absolute inset-0 flex" style={{ left: 160 }}>
            {days.map((day, i) => {
              const isGray = day.getDay() === 0 || day.getDay() === 6 || holidaySet.has(toISODate(day));
              return (
                <div
                  key={i}
                  style={{ width: DAY_WIDTH }}
                  className={`shrink-0 ${isGray ? "bg-black/[0.04]" : ""}`}
                />
              );
            })}
          </div>

          {[...floorsByGroup.entries()].map(([groupName, floors]) => (
            <div key={groupName}>
              <div className="sticky left-0 z-10 w-[160px] border-b border-black/10 bg-pmon-yellow/10 px-3 py-1 text-xs font-semibold text-black/70">
                {groupName}
              </div>
              {floors.map((floor) => {
                const tracks = partitionIntoTracks(cyclesByFloor.get(floor.id) ?? []);
                const rowHeight = Math.max(1, tracks.length) * ROW_HEIGHT;
                return (
                  <div key={floor.id} className="flex border-b border-black/5" style={{ height: rowHeight }}>
                    <div className="sticky left-0 z-10 flex w-[160px] shrink-0 items-center border-r border-black/10 bg-white px-3 text-sm text-black">
                      {floor.floorName}
                    </div>
                    <div className="relative" style={{ width: totalWidth, height: rowHeight }}>
                      {tracks.map((track, trackIndex) =>
                        track.map((item) => {
                          const service = serviceById.get(item.serviceId);
                          return (
                            <div
                              key={item.cycleId}
                              title={service?.name}
                              style={{
                                position: "absolute",
                                left: barLeft(item.start),
                                width: barWidth(item.start, item.end),
                                top: trackIndex * ROW_HEIGHT + 4,
                                height: ROW_HEIGHT - 8,
                                backgroundColor: service?.color ?? "#F5C400",
                              }}
                              className="truncate rounded px-1 text-[10px] leading-[24px] text-white"
                            >
                              {service?.name}
                            </div>
                          );
                        }),
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
