import type { ModuleCode } from "@/lib/api/modules";
import type { Team } from "@/types/team";

// Gestão de acesso por módulo e time (tela /usuarios, só pro master).
// Espelha profile_modules (019), team_members (015) e profiles.system_role
// (015/043). A segurança real é a RLS: só o master (is_master(), 043/044)
// lê e grava essas linhas.

export type { ModuleCode };

export const MODULES: readonly { code: ModuleCode; label: string }[] = [
  { code: "crm", label: "CRM" },
  { code: "financeiro", label: "Financeiro" },
  { code: "engenharia", label: "Engenharia" },
  { code: "reembolso", label: "Reembolso" },
];

export type PartnerTier = "founding" | "associate";

export const PARTNER_TIER_LABEL: Record<PartnerTier, string> = {
  founding: "Fundador",
  associate: "Associado",
};

export interface TeamMembership {
  id: string;
  teamId: string;
  partnerTier: PartnerTier | null;
  isLead: boolean;
}

export interface ProfileAccess {
  profileId: string;
  systemRole: string | null;
  modules: ModuleCode[];
  // Array porque o banco só garante unique (team_id, profile_id): a regra
  // "um time por usuário" é da tela, e ela avisa se aparecer mais de um.
  teams: TeamMembership[];
}

export interface AccessData {
  isMaster: boolean;
  profiles: Record<string, ProfileAccess>;
  teams: Team[];
}

// getAccessData() nunca derruba a página: em caso de erro, /usuarios
// continua funcionando e só a seção de módulos e times mostra o aviso.
export type AccessResult = { ok: true; data: AccessData } | { ok: false; error: string };
