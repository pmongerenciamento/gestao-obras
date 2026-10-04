// Tradução dos erros do banco na gestão de acesso (mesmo padrão de
// client-mutations.ts, que olha error.code do PostgrestError). As mensagens
// de 42501 vêm da RLS ou dos triggers da 043 (trg_profiles_guard_system_role
// e trg_profiles_protect_last_master).

interface DbError {
  code?: string;
  message?: string;
}

export const ONLY_MASTER_DELETE_MESSAGE =
  "Não é possível excluir o único master. Promova outro master antes (pelo administrador do banco).";

export const TEAM_MEMBER_DELETE_MESSAGE =
  "Este usuário está em um time. Remova-o do time em \"Módulos e time\" antes de excluir a conta.";

export function translateAccessError(error: unknown): string {
  const { code, message = "" } = (error ?? {}) as DbError;

  if (code === "42501") {
    if (message.includes("único master")) {
      return "Não é possível rebaixar ou excluir o único master. Promova outro master antes.";
    }
    if (message.includes("system_role")) {
      return "O papel de master só pode ser alterado pelo administrador do banco.";
    }
    return "Só o usuário master pode alterar acessos.";
  }
  if (code === "23503") return "Usuário ou time não encontrado. Recarregue a página.";
  if (code === "23505") return "Esse acesso já existe.";
  return "Não foi possível salvar. Tente novamente.";
}
