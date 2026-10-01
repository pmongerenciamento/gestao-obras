import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura do nome de exibição do usuário logado (backend/migrations/005_users_and_members.sql).
// Usado na saudação da tela inicial — auth.users tem e-mail, mas o nome fica em profiles.

export async function getProfileFullName(userId: string): Promise<string | null> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("profiles")
    .select("full_name")
    .eq("id", userId)
    .single();

  if (error || !data) return null;
  return data.full_name;
}
