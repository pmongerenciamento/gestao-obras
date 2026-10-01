import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import type { NewClientInput } from "@/types/client";

// Só client-side (mesmo padrão de lib/api/project-mutations.ts).

export async function createClient(input: NewClientInput): Promise<string> {
  const supabase = createSupabaseClient();

  const { data, error } = await supabase
    .from("clients")
    .insert({
      code: input.code,
      legal_name: input.legalName,
      contact_name: input.contactName || null,
      contact_email: input.contactEmail || null,
      contact_phone: input.contactPhone || null,
      notes: input.notes || null,
    })
    .select("id")
    .single();

  if (error) {
    // 23505 = unique_violation (Postgres) — só a constraint de `code` é unique nesta tabela.
    if (error.code === "23505") {
      throw new Error(`Já existe um cliente com o código ${input.code}.`);
    }
    throw error;
  }
  if (!data) throw new Error("Falha ao criar o cliente.");

  return data.id;
}
