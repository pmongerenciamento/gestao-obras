// Saudação e data por extenso da tela inicial. Fixado em America/Sao_Paulo
// (não no timezone do servidor) pra bater com o horário real da equipe PMON
// independente de onde o Next roda em produção (Vercel costuma ser UTC).

const TIMEZONE = "America/Sao_Paulo";

export function getGreeting(): string {
  const hour =
    Number(
      new Intl.DateTimeFormat("pt-BR", {
        hour: "numeric",
        hour12: false,
        timeZone: TIMEZONE,
      }).format(new Date()),
    ) % 24;

  if (hour >= 5 && hour < 12) return "Bom dia";
  if (hour >= 12 && hour < 18) return "Boa tarde";
  return "Boa noite";
}

export function getFullDateExtenso(): string {
  const formatted = new Intl.DateTimeFormat("pt-BR", {
    timeZone: TIMEZONE,
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());

  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}
