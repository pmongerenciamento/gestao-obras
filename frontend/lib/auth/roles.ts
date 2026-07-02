// TODO: substituir por um campo de role real quando o backend tiver esse conceito
// (hoje `projects` só tem `owner_id`, sem tabela de membros/roles).
const MASTER_EMAILS = ["diego@pmongerenciamento.com.br"];

export function isMasterUser(email: string | undefined | null): boolean {
  if (!email) return false;
  return MASTER_EMAILS.some((masterEmail) => masterEmail.toLowerCase() === email.toLowerCase());
}
