import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Lê os módulos do usuário logado (profile_modules, migration 019). O filtro
// por profile_id é obrigatório: com a policy profile_modules_select_master
// (043), o master enxerga as linhas de todos.

export type ModuleCode = "crm" | "financeiro" | "engenharia" | "reembolso";

interface ProfileModuleRow {
  module: ModuleCode;
}

export async function listUserModules(): Promise<ModuleCode[]> {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return [];

  const { data, error } = await supabase
    .from("profile_modules")
    .select("module")
    .eq("profile_id", user.id);

  if (error || !data) return [];
  return (data as ProfileModuleRow[]).map((row) => row.module);
}
