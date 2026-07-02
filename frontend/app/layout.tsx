import type { ReactNode } from "react";
import type { Metadata } from "next";
import "./globals.css";

// Layout raiz do Next.js: fontes globais e tema PMON (preto #0D0D0D, branco, amarelo #F5C400)

export const metadata: Metadata = {
  title: "Gestão de Obras",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
