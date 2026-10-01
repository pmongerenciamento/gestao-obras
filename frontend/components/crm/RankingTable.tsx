import type { RankingEntry } from "@/types/crm";

interface RankingTableProps {
  ranking: RankingEntry[];
}

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

export function RankingTable({ ranking }: RankingTableProps) {
  return (
    <div className="rounded-lg border border-black/10 bg-white">
      <div className="border-b border-black/10 p-4">
        <h2 className="text-sm font-semibold text-black/70">Ranking do período</h2>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
          <tr>
            <th className="px-4 py-3 font-medium">Responsável</th>
            <th className="px-4 py-3 font-medium">Propostas aceitas</th>
            <th className="px-4 py-3 font-medium">Total</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((entry) => (
            <tr key={entry.ownerId} className="border-b border-black/5 last:border-0">
              <td className="px-4 py-3 text-black">{entry.displayName}</td>
              <td className="px-4 py-3 text-black/70">{entry.count}</td>
              <td className="px-4 py-3 text-black/70">{formatBRL(entry.totalValue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ranking.length === 0 && (
        <p className="px-4 py-8 text-center text-sm text-black/50">
          Nenhuma proposta aceita neste mês ainda.
        </p>
      )}
    </div>
  );
}
