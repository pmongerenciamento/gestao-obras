import type { CrmKpis } from "@/types/crm";

interface KpiGridProps {
  kpis: CrmKpis;
}

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

export function KpiGrid({ kpis }: KpiGridProps) {
  const cards: { label: string; value: string; sub?: string }[] = [
    { label: "Prospects novos", value: String(kpis.novosProspects) },
    { label: "Propostas enviadas", value: String(kpis.propostasEnviadas) },
    { label: "Taxa de conversão", value: formatPercent(kpis.taxaConversao) },
    { label: "Ticket médio", value: kpis.ticketMedio === null ? "—" : formatBRL(kpis.ticketMedio) },
    {
      label: "Em negociação",
      value: formatBRL(kpis.emNegociacaoValue),
      sub: `${kpis.emNegociacaoCount} proposta${kpis.emNegociacaoCount === 1 ? "" : "s"}`,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => (
        <div key={card.label} className="rounded-lg border border-black/10 bg-white p-4">
          <p className="text-xs text-black/50">{card.label}</p>
          <p className="mt-1 text-xl font-semibold text-black">{card.value}</p>
          {card.sub && <p className="text-xs text-black/40">{card.sub}</p>}
        </div>
      ))}
    </div>
  );
}
