import type { ReactNode } from "react";

// Layout da área autenticada: Topbar é renderizado por cada tela (painel/projeto), não aqui —
// cada uma precisa de um breadcrumb diferente (ver components/layout/Header.tsx).

export default function AppLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-pmon-bg text-pmon-black">{children}</div>;
}
