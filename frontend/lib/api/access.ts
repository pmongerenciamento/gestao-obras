import type { ModuleCode } from "@/lib/api/modules";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";
import type { AccessData, AccessResult, PartnerTier, ProfileAccess } from "@/types/access";

// Leitura server-side da gestão de acesso (tela /usuarios). Só o master lê
// tudo: profile_modules e team_members pelas policies "for all" da 043, teams
// pela teams_select_master (044). Pra quem não é master, devolve isMaster
// false sem ler mais nada. Nunca lança erro — ver AccessResult.

interface ProfileRow {
  id: string;
  system_role: string | null;
}

interface ProfileModuleRow {
  profile_id: string;
  module: ModuleCode;
}

interface TeamMemberRow {
  id: string;
  team_id: string;
  profile_id: string;
  partner_tier: PartnerTier | null;
  is_lead: boolean;
}

const LOAD_ERROR = "Não foi possível carregar módulos e times. Recarregue a página.";

export async function getAccessData(): Promise<AccessResult> {
  try {
    const supabase = await createSupabaseServerClient();

    const { data: isMaster, error: masterError } = await supabase.rpc("is_master");
    if (masterError) return { ok: false, error: LOAD_ERROR };
    if (!isMaster) return { ok: true, data: { isMaster: false, profiles: {}, teams: [] } };

    const [profilesRes, modulesRes, membersRes, teamsRes] = await Promise.all([
      supabase.from("profiles").select("id, system_role"),
      supabase.from("profile_modules").select("profile_id, module"),
      supabase.from("team_members").select("id, team_id, profile_id, partner_tier, is_lead"),
      supabase.from("teams").select("id, name").order("name"),
    ]);
    if (profilesRes.error || modulesRes.error || membersRes.error || teamsRes.error) {
      return { ok: false, error: LOAD_ERROR };
    }

    const profiles: Record<string, ProfileAccess> = {};
    for (const row of (profilesRes.data ?? []) as ProfileRow[]) {
      profiles[row.id] = { profileId: row.id, systemRole: row.system_role, modules: [], teams: [] };
    }
    for (const row of (modulesRes.data ?? []) as ProfileModuleRow[]) {
      profiles[row.profile_id]?.modules.push(row.module);
    }
    for (const row of (membersRes.data ?? []) as TeamMemberRow[]) {
      profiles[row.profile_id]?.teams.push({
        id: row.id,
        teamId: row.team_id,
        partnerTier: row.partner_tier,
        isLead: row.is_lead,
      });
    }

    const data: AccessData = { isMaster: true, profiles, teams: teamsRes.data ?? [] };
    return { ok: true, data };
  } catch {
    return { ok: false, error: LOAD_ERROR };
  }
}
