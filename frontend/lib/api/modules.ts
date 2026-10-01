import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura de profile_modules (backend/migrations/019_create_profile_modules.sql)
// — RLS (profile_modules_select_own) já restringe a leitura às linhas do
// próprio usuário logado, sem precisar filtrar por profile_id aqui.

export type ModuleCode = "crm" | "financeiro" | "engenharia" | "reembolso";

interface ProfileModuleRow {
  module: ModuleCode;
}

export async function listUserModules(): Promise<ModuleCode[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("profile_modules").select("module");

  if (error || !data) return [];
  return (data as ProfileModuleRow[]).map((row) => row.module);
}
