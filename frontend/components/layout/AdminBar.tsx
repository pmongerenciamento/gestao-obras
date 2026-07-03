import Link from "next/link";

// Barra de admin no rodapé do painel, visível só pra usuário master (ver lib/auth/roles.ts).
// "Configurações" continua placeholder, mesmo padrão do "Esqueceu a senha?" do login.

export function AdminBar() {
  return (
    <div className="mt-auto flex items-center justify-center gap-6 border-t border-black/10 pt-8 pb-4 text-sm text-black/50">
      <Link href="/usuarios" className="hover:text-black/70">
        Gerenciar usuários
      </Link>
      <span className="cursor-not-allowed hover:text-black/70">Configurações</span>
    </div>
  );
}
