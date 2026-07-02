// Máscaras de exibição pt-BR pra campos numéricos do formulário. O valor
// enviado ao banco continua puramente numérico — só a apresentação usa essas
// funções (ver components/projects/NewProjectForm.tsx).

export function parseDigits(value: string): string {
  return value.replace(/\D/g, "");
}

// "32000" -> "32.000"
export function formatThousands(rawDigits: string): string {
  if (!rawDigits) return "";
  return new Intl.NumberFormat("pt-BR").format(Number(rawDigits));
}

// "12000000000" (centavos) -> "R$ 120.000.000,00"
export function formatCurrencyBRL(rawDigitsCents: string): string {
  if (!rawDigitsCents) return "";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    Number(rawDigitsCents) / 100,
  );
}
