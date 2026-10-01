// Primeiro/último dia do mês atual em America/Sao_Paulo (mesmo timezone fixo
// de lib/date/greeting.ts) — usado como período padrão, editável, do novo
// relatório de reembolso.

const TIMEZONE = "America/Sao_Paulo";

export function getCurrentMonthRange(): { start: string; end: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TIMEZONE,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());

  const year = Number(parts.find((p) => p.type === "year")!.value);
  const month = Number(parts.find((p) => p.type === "month")!.value); // 1-12

  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();

  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    start: `${year}-${pad(month)}-01`,
    end: `${year}-${pad(month)}-${pad(lastDay)}`,
  };
}
