"use client";

import { useState } from "react";
import type { Team } from "@/types/team";
import type { User } from "@/types/user";
import {
  MODULES,
  PARTNER_TIER_LABEL,
  type ModuleCode,
  type PartnerTier,
  type ProfileAccess,
} from "@/types/access";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Select } from "@/components/ui/Select";
import { grantModule, removeTeam, revokeModule, setTeam } from "@/lib/api/access-mutations";

// Modal de módulos e time de 1 usuário (tela /usuarios, só pro master).
// Grava direto no Supabase (lib/api/access-mutations.ts) — a RLS da 043/044
// é quem garante que só o master consegue. Mesmo padrão visual de overlay
// do AccessModal. Módulos e times vêm sempre das props (recarregadas com
// router.refresh() depois de cada gravação), sem cópia em state.

interface ModuleTeamModalProps {
  user: User;
  access: ProfileAccess | undefined;
  teams: Team[];
  isSelf: boolean;
  onClose: () => void;
  onChanged: () => void;
}

type PendingConfirm = { kind: "module"; module: ModuleCode } | { kind: "team"; membershipId: string };

const SELF_NOTE =
  "Isso não tira o seu papel de master nem o acesso a /usuarios, e você pode conceder os módulos de volta quando quiser.";

function moduleLabel(code: ModuleCode): string {
  return MODULES.find((m) => m.code === code)?.label ?? code;
}

export function ModuleTeamModal({ user, access, teams, isSelf, onClose, onChanged }: ModuleTeamModalProps) {
  const current = access?.teams[0];
  const [teamId, setTeamId] = useState(current?.teamId ?? "");
  const [partnerTier, setPartnerTier] = useState<PartnerTier | "">(current?.partnerTier ?? "");
  const [isLead, setIsLead] = useState(current?.isLead ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const displayName = user.fullName ?? user.email;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  function handleToggleModule(module: ModuleCode, checked: boolean) {
    if (!access) return;
    if (checked) {
      void run(() => grantModule(access.profileId, module));
    } else if (isSelf) {
      setPending({ kind: "module", module });
    } else {
      void run(() => revokeModule(access.profileId, module));
    }
  }

  function handleSaveTeam() {
    if (!access || !teamId) return;
    void run(() =>
      setTeam(access.profileId, { teamId, partnerTier: partnerTier || null, isLead }, current?.id),
    );
  }

  function handleRemoveTeam(membershipId: string) {
    if (isSelf) {
      setPending({ kind: "team", membershipId });
      return;
    }
    void run(async () => {
      await removeTeam(membershipId);
      if (membershipId === current?.id) {
        setTeamId("");
        setPartnerTier("");
        setIsLead(false);
      }
    });
  }

  async function handleConfirm() {
    if (!access || !pending) return;
    const target = pending;
    setPending(null);
    if (target.kind === "module") {
      await run(() => revokeModule(access.profileId, target.module));
    } else {
      await run(async () => {
        await removeTeam(target.membershipId);
        if (target.membershipId === current?.id) {
          setTeamId("");
          setPartnerTier("");
          setIsLead(false);
        }
      });
    }
  }

  const confirmTitle = pending?.kind === "team" ? "Sair do time" : "Remover módulo";
  const confirmDescription =
    pending?.kind === "module"
      ? `Remover o módulo ${moduleLabel(pending.module)} do seu próprio perfil? Você deixa de acessar esse módulo. ${SELF_NOTE}`
      : `Remover você mesmo do time? Isso não tira o seu papel de master nem o acesso a /usuarios, e você pode se colocar de volta quando quiser.`;

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
        <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
          <h2 className="text-lg font-semibold text-black">Módulos e time</h2>
          <p className="mt-1 text-sm text-black/60">{displayName}</p>

          {!access ? (
            <p className="mt-6 rounded-md bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
              Este usuário ainda não tem perfil. Módulos e time ficam disponíveis depois que o perfil for criado.
            </p>
          ) : (
            <>
              <div className="mt-6 flex flex-col gap-2">
                <h3 className="text-sm font-semibold text-black/70">Módulos</h3>
                {MODULES.map(({ code, label }) => (
                  <label key={code} className="flex items-center gap-2 text-sm text-black">
                    <input
                      type="checkbox"
                      checked={access.modules.includes(code)}
                      disabled={busy}
                      onChange={(e) => handleToggleModule(code, e.target.checked)}
                    />
                    {label}
                  </label>
                ))}
              </div>

              <div className="mt-6 flex flex-col gap-3">
                <h3 className="text-sm font-semibold text-black/70">Time</h3>
                {access.teams.length > 1 && (
                  <div className="rounded-md bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
                    <p>Este usuário está em mais de um time. Mantenha só um:</p>
                    <ul className="mt-2 flex flex-col gap-1">
                      {access.teams.map((membership) => (
                        <li key={membership.id} className="flex items-center justify-between">
                          <span>{teams.find((t) => t.id === membership.teamId)?.name ?? "Time desconhecido"}</span>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleRemoveTeam(membership.id)}
                            className="text-xs font-medium text-red-600 hover:underline disabled:opacity-60"
                          >
                            Remover
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <Select
                  id="team"
                  label="Time"
                  placeholder="Sem time"
                  options={teams.map((t) => ({ value: t.id, label: t.name }))}
                  value={teamId}
                  disabled={busy}
                  onChange={(e) => setTeamId(e.target.value)}
                />
                <Select
                  id="partnerTier"
                  label="Categoria de sócio"
                  placeholder="Sem categoria"
                  options={(Object.keys(PARTNER_TIER_LABEL) as PartnerTier[]).map((tier) => ({
                    value: tier,
                    label: PARTNER_TIER_LABEL[tier],
                  }))}
                  value={partnerTier}
                  disabled={busy || !teamId}
                  onChange={(e) => setPartnerTier(e.target.value as PartnerTier | "")}
                />
                <label className="flex items-center gap-2 text-sm text-black">
                  <input
                    type="checkbox"
                    checked={isLead}
                    disabled={busy || !teamId}
                    onChange={(e) => setIsLead(e.target.checked)}
                  />
                  Líder do time
                </label>
                <div className="flex justify-end gap-2">
                  {current && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleRemoveTeam(current.id)}
                      className="rounded-md bg-black/10 px-3 py-1.5 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Tirar do time
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy || !teamId}
                    onClick={handleSaveTeam}
                    className="rounded-md bg-pmon-yellow px-3 py-1.5 text-sm font-semibold text-pmon-black hover:bg-pmon-yellow/90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Salvar time
                  </button>
                </div>
              </div>
            </>
          )}

          {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15"
            >
              Fechar
            </button>
          </div>
        </div>
      </div>

      {/* Fora do overlay do modal: clique no fundo do diálogo não pode fechar o modal junto. */}
      <ConfirmDialog
        open={pending !== null}
        title={confirmTitle}
        description={confirmDescription}
        confirmLabel="Remover"
        onConfirm={handleConfirm}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
