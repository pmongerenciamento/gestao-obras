import type { Team } from "@/types/team";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura de teams (backend/migrations/015_create_teams.sql). RLS
// (teams_read, has_permission('teams','read')) só libera pra quem tem o
// módulo financeiro — única linha de 'teams' no catálogo (023).

export async function listTeams(): Promise<Team[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("teams").select("id, name").order("name");

  if (error || !data) return [];
  return data;
}
