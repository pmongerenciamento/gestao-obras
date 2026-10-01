import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import type { CloseDealInput } from "@/types/close-deal";

// Só client-side. close_deal() (backend/migrations/029_close_deal_function.sql)
// faz tudo numa função plpgsql (uma transação implícita só) — sem risco de
// escrita parcial, diferente das outras mutações deste app que fazem writes
// sequenciais em tabelas separadas.

export async function closeDeal(input: CloseDealInput): Promise<string> {
  const supabase = createSupabaseClient();

  const { data, error } = await supabase.rpc("close_deal", {
    p_project_id: input.projectId,
    p_client_legal_name: input.clientLegalName,
    p_client_cnpj: input.clientCnpj,
    p_client_address: input.clientAddress,
    p_legal_rep_name: input.legalRepName,
    p_legal_rep_cpf: input.legalRepCpf,
    p_legal_rep_role: input.legalRepRole,
    p_spe_legal_name: input.speLegalName,
    p_spe_cnpj: input.speCnpj,
    p_spe_address: input.speAddress,
    p_team_id: input.teamId,
  });

  // raise exception vira PostgrestError com a mensagem original em .message
  // (ex.: "Projeto sem cliente vinculado") — repassa direto, é legível.
  if (error) throw new Error(error.message);
  return data as string;
}
