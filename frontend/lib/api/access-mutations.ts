import type { ModuleCode } from "@/lib/api/modules";
import { translateAccessError } from "@/lib/api/access-errors";
import { createClient } from "@/lib/supabase/client";
import type { PartnerTier } from "@/types/access";

// Escrita client-side da gestão de acesso, direto no Supabase (sem backend):
// a RLS da 043 só deixa o master gravar em profile_modules e team_members.
// Quem chama recarrega a tela com router.refresh() depois. Erros saem já
// traduzidos (access-errors.ts).

export async function grantModule(profileId: string, module: ModuleCode): Promise<void> {
  const supabase = createClient();
  const { error } = await supabase.from("profile_modules").insert({ profile_id: profileId, module });
  // 23505 = já existe (alguém concedeu antes): o estado final é o mesmo.
  if (error && error.code !== "23505") throw new Error(translateAccessError(error));
}

export async function revokeModule(profileId: string, module: ModuleCode): Promise<void> {
  const supabase = createClient();
  const { error } = await supabase
    .from("profile_modules")
    .delete()
    .eq("profile_id", profileId)
    .eq("module", module);
  if (error) throw new Error(translateAccessError(error));
}

interface TeamInput {
  teamId: string;
  partnerTier: PartnerTier | null;
  isLead: boolean;
}

// Um time por usuário: se já existe uma linha, atualiza a mesma (um único
// statement), em vez de apagar e inserir — duas requisições separadas
// deixariam o usuário sem time se a segunda falhasse.
export async function setTeam(profileId: string, input: TeamInput, existingId?: string): Promise<void> {
  const supabase = createClient();
  const row = { team_id: input.teamId, partner_tier: input.partnerTier, is_lead: input.isLead };
  const { error } = existingId
    ? await supabase.from("team_members").update(row).eq("id", existingId)
    : await supabase.from("team_members").insert({ ...row, profile_id: profileId });
  if (error) throw new Error(translateAccessError(error));
}

export async function removeTeam(membershipId: string): Promise<void> {
  const supabase = createClient();
  const { error } = await supabase.from("team_members").delete().eq("id", membershipId);
  if (error) throw new Error(translateAccessError(error));
}
