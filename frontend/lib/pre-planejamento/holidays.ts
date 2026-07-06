// Feriados nacionais brasileiros — fixos + móveis (calculados a partir da
// Páscoa, algoritmo de Gauss/computus). Usado pra pré-popular sim_holidays
// quando um estudo é criado. Espelha
// backend/app/domain/pre_planejamento/holidays.py — mesmo algoritmo, mesmas
// datas, só migrado pro client-side já que createStudy agora grava direto no
// Supabase (ver lib/api/pre-planejamento-mutations.ts).

const FIXED_HOLIDAYS: Array<[month: number, day: number, description: string]> = [
  [1, 1, "Confraternização Universal"],
  [4, 21, "Tiradentes"],
  [5, 1, "Dia do Trabalho"],
  [9, 7, "Independência do Brasil"],
  [10, 12, "Nossa Senhora Aparecida"],
  [11, 2, "Finados"],
  [11, 15, "Proclamação da República"],
  [12, 25, "Natal"],
];

export interface GeneratedHoliday {
  date: string;
  description: string;
}

function toISODate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function easterDate(year: number): Date {
  // Algoritmo de Gauss (computus) pra domingo de Páscoa no calendário gregoriano.
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}

export function generateNationalHolidays(startYear: number, numYears = 4): GeneratedHoliday[] {
  const holidays: GeneratedHoliday[] = [];
  for (let year = startYear; year < startYear + numYears; year++) {
    for (const [month, day, description] of FIXED_HOLIDAYS) {
      holidays.push({ date: toISODate(new Date(year, month - 1, day)), description });
    }

    const easter = easterDate(year);
    holidays.push({ date: toISODate(addDays(easter, -47)), description: "Carnaval" });
    holidays.push({ date: toISODate(addDays(easter, -2)), description: "Sexta-feira Santa" });
    holidays.push({ date: toISODate(addDays(easter, 60)), description: "Corpus Christi" });
  }
  return holidays;
}
