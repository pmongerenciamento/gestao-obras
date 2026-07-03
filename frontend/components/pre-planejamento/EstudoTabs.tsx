"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface EstudoTabsProps {
  baseHref: string;
}

const TABS = [
  { slug: "calendario", label: "Calendário" },
  { slug: "servicos", label: "Serviços e lotes" },
  { slug: "linha-de-balanco", label: "Linha de balanço" },
];

export function EstudoTabs({ baseHref }: EstudoTabsProps) {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 border-b border-black/10">
      {TABS.map((tab) => {
        const href = `${baseHref}/${tab.slug}`;
        const active = pathname === href;
        return (
          <Link
            key={tab.slug}
            href={href}
            className={`border-b-2 px-4 py-2 text-sm ${
              active
                ? "border-pmon-yellow font-medium text-pmon-black"
                : "border-transparent text-black/60 hover:text-black"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
