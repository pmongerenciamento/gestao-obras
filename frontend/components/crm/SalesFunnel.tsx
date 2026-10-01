import type { FunnelStage } from "@/types/crm";

interface SalesFunnelProps {
  funnel: FunnelStage[];
}

export function SalesFunnel({ funnel }: SalesFunnelProps) {
  const maxCount = Math.max(1, ...funnel.map((stage) => stage.count));

  return (
    <div className="rounded-lg border border-black/10 bg-white p-4">
      <h2 className="mb-4 text-sm font-semibold text-black/70">Funil de vendas</h2>
      <div className="flex flex-col gap-3">
        {funnel.map((stage) => (
          <div key={stage.stage} className="flex items-center gap-3">
            <span className="w-32 shrink-0 text-xs text-black/60">{stage.label}</span>
            <div className="h-5 flex-1 rounded bg-black/5">
              <div
                className="h-5 rounded bg-pmon-yellow"
                style={{ width: `${(stage.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="w-8 shrink-0 text-right text-xs font-medium text-black">{stage.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
