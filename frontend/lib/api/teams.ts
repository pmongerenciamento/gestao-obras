import type { Team } from "@/types/team";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura de teams (backend/migrations/015_create_teams.sql). RLS
// (teams_read, has_permission('teams','read')) já libera pro módulo CRM.

export async function listTeams(): Promise<Team[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("teams").select("id, name").order("name");

  if (error || !data) return [];
  return data;
}
