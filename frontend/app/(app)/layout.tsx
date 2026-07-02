import type { ReactNode } from "react";

// Layout da área autenticada: Sidebar + Header (nome do usuário logado e logout)
// TODO: Sidebar e Header ainda são stubs (components/layout/) — layout minimo por enquanto.

export default function AppLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-pmon-black text-white">{children}</div>;
}
