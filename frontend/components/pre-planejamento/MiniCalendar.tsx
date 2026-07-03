"use client";

import { useState } from "react";
import { IconChevronLeft, IconChevronRight } from "@tabler/icons-react";
import type { Holiday } from "@/types/pre-planejamento";
import { parseISODate, toISODate } from "@/lib/pre-planejamento/scheduler";

// Mini calendário visual (aba Calendário) — dias coloridos por tipo, mesmo
// padrão de cores do mockup docs/mockups/pre-plan-calendario.html.

const WEEKDAY_HEADERS = ["S", "T", "Q", "Q", "S", "S", "D"];

interface MiniCalendarProps {
  initialMonth: string;
  holidays: Holiday[];
}

function daysSinceMonday(date: Date): number {
  return (date.getDay() + 6) % 7;
}

export function MiniCalendar({ initialMonth, holidays }: MiniCalendarProps) {
  const initial = parseISODate(initialMonth);
  const [year, setYear] = useState(initial.getFullYear());
  const [month, setMonth] = useState(initial.getMonth());

  const holidaysByDate = new Map(holidays.map((h) => [h.date, h]));

  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const leadingEmpty = daysSinceMonday(first);

  const cells: (number | null)[] = [
    ...Array<null>(leadingEmpty).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  function goToPreviousMonth() {
    if (month === 0) {
      setYear((y) => y - 1);
      setMonth(11);
    } else {
      setMonth((m) => m - 1);
    }
  }

  function goToNextMonth() {
    if (month === 11) {
      setYear((y) => y + 1);
      setMonth(0);
    } else {
      setMonth((m) => m + 1);
    }
  }

  const monthLabel = new Date(year, month, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <button type="button" onClick={goToPreviousMonth} className="text-black/40 hover:text-black">
          <IconChevronLeft size={18} />
        </button>
        <span className="text-sm font-semibold capitalize text-black">{monthLabel}</span>
        <button type="button" onClick={goToNextMonth} className="text-black/40 hover:text-black">
          <IconChevronRight size={18} />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {WEEKDAY_HEADERS.map((label, i) => (
          <div key={i} className="pb-1 text-center text-[11px] text-black/40">
            {label}
          </div>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <div key={i} />;
          const date = new Date(year, month, day);
          const iso = toISODate(date);
          const holiday = holidaysByDate.get(iso);
          const isWeekend = date.getDay() === 0 || date.getDay() === 6;

          let className = "bg-black/[0.03] text-black/70";
          if (isWeekend) className = "bg-black/10 text-black/40";
          if (holiday?.isNational) className = "bg-orange-400 text-white font-semibold";
          else if (holiday) className = "bg-blue-500 text-white font-semibold";

          return (
            <div
              key={i}
              className={`flex aspect-square items-center justify-center rounded-md text-xs ${className}`}
              title={holiday?.description}
            >
              {day}
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex flex-col gap-2 text-xs text-black/60">
        <div className="flex items-center gap-2">
          <span className="h-3.5 w-3.5 rounded bg-black/10" /> Fim de semana
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3.5 w-3.5 rounded bg-orange-400" /> Feriado nacional
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3.5 w-3.5 rounded bg-blue-500" /> Feriado personalizado
        </div>
      </div>
    </div>
  );
}
