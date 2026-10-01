import Link from "next/link";
import { HOME_MODULES } from "@/lib/home-modules";
import type { ModuleCode } from "@/lib/api/modules";

interface ModuleGridProps {
  userModules: ModuleCode[];
}

export function ModuleGrid({ userModules }: ModuleGridProps) {
  // 'reembolso' não segue o sistema de permissões por módulo — é aberto a
  // qualquer autenticado, então aparece pra todo mundo independente de
  // profile_modules (RLS de reimbursement_reports/items é quem protege os dados).
  const visibleModules = HOME_MODULES.filter(
    (module) => module.code === "reembolso" || userModules.includes(module.code),
  );

  if (visibleModules.length === 0) {
    return (
      <div className="rounded-lg border border-black/10 bg-white p-8 text-center text-sm text-black/50">
        Você ainda não tem acesso a nenhum módulo — contate um administrador.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {visibleModules.map((module) =>
        module.href ? (
          <Link
            key={module.code}
            href={module.href}
            className="flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-4 transition-colors hover:border-pmon-yellow hover:shadow-md"
          >
            <module.icon size={24} className="text-pmon-black/70" />
            <span className="font-medium text-black">{module.label}</span>
            <p className="text-xs text-black/50">{module.description}</p>
          </Link>
        ) : (
          <div
            key={module.code}
            className="relative flex flex-col gap-2 rounded-lg border border-black/10 bg-white p-4 opacity-60"
          >
            <span className="absolute right-3 top-3 rounded-full bg-black/5 px-2 py-0.5 text-[10px] font-medium text-black/50">
              Em breve
            </span>
            <module.icon size={24} className="text-pmon-black/70" />
            <span className="font-medium text-black">{module.label}</span>
            <p className="text-xs text-black/50">{module.description}</p>
          </div>
        ),
      )}
    </div>
  );
}
