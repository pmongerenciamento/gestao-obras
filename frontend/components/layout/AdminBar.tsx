// Barra de admin no rodapé do painel, visível só pra usuário master (ver lib/auth/roles.ts).
// Sem rota própria ainda — links são placeholders, mesmo padrão do "Esqueceu a senha?" do login.

export function AdminBar() {
  return (
    <div className="mt-auto flex items-center justify-center gap-6 border-t border-black/10 pt-8 pb-4 text-sm text-black/50">
      <span className="cursor-not-allowed hover:text-black/70">Gerenciar usuários</span>
      <span className="cursor-not-allowed hover:text-black/70">Configurações</span>
    </div>
  );
}
