"use client";

import { useState } from "react";
import Image from "next/image";
import type { ProjectOption, User } from "@/types/user";
import { Select } from "@/components/ui/Select";
import { grantAccess, setAvatar, updateUser, uploadAvatar } from "@/lib/api/user-mutations";

// Modal de gestão de acesso de 1 usuário: revogar/reativar acesso a um
// projeto específico (project_members.status), conceder acesso a um projeto
// novo e trocar o avatar. Mesmo padrão visual de overlay do NewUserModal.

const STATUS_LABEL: Record<string, string> = {
  pending: "Convite pendente",
  active: "Ativo",
  blocked: "Bloqueado",
};

interface AccessModalProps {
  user: User;
  projects: ProjectOption[];
  onClose: () => void;
  onChanged: () => void;
}

export function AccessModal({ user, projects, onClose, onChanged }: AccessModalProps) {
  const [busyProjectId, setBusyProjectId] = useState<string | null>(null);
  const [addProjectId, setAddProjectId] = useState("");
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availableProjects = projects.filter(
    (project) => !user.memberships.some((m) => m.projectId === project.id),
  );

  async function handleToggleMembership(projectId: string, currentStatus: string) {
    setBusyProjectId(projectId);
    setError(null);
    try {
      await updateUser(user.id, currentStatus === "blocked" ? "unblock" : "block", projectId);
      onChanged();
    } catch {
      setError("Não foi possível atualizar o acesso. Tente novamente.");
    } finally {
      setBusyProjectId(null);
    }
  }

  async function handleGrant() {
    if (!addProjectId) return;
    setBusyProjectId(addProjectId);
    setError(null);
    try {
      await grantAccess(user.id, addProjectId);
      setAddProjectId("");
      onChanged();
    } catch {
      setError("Não foi possível conceder o acesso. Tente novamente.");
    } finally {
      setBusyProjectId(null);
    }
  }

  async function handleAvatarChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadingAvatar(true);
    setError(null);
    try {
      const url = await uploadAvatar(file);
      await setAvatar(user.id, url);
      onChanged();
    } catch {
      setError("Não foi possível atualizar a foto. Tente novamente.");
    } finally {
      setUploadingAvatar(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-black">Gerenciar acesso</h2>
        <p className="mt-1 text-sm text-black/60">{user.fullName ?? user.email}</p>

        <div className="mt-4 flex items-center gap-4">
          {user.avatarUrl ? (
            <Image
              src={user.avatarUrl}
              alt={user.fullName ?? user.email}
              width={48}
              height={48}
              className="h-12 w-12 rounded-full object-cover"
            />
          ) : (
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-pmon-black text-sm font-semibold text-white">
              {(user.fullName ?? user.email).charAt(0).toUpperCase()}
            </div>
          )}
          <label className="text-sm text-black/70">
            <span className="cursor-pointer text-pmon-black underline">
              {uploadingAvatar ? "Enviando..." : "Trocar foto"}
            </span>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={uploadingAvatar}
              onChange={handleAvatarChange}
            />
          </label>
        </div>

        <div className="mt-6 flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-black/70">Projetos</h3>
          {user.memberships.length === 0 && (
            <p className="text-sm text-black/40">Sem acesso a nenhum projeto ainda.</p>
          )}
          {user.memberships.map((membership) => (
            <div
              key={membership.projectId}
              className="flex items-center justify-between rounded-md border border-black/10 px-3 py-2 text-sm"
            >
              <div>
                <p className="text-black">{membership.projectName}</p>
                <p className="text-xs text-black/50">{STATUS_LABEL[membership.status]}</p>
              </div>
              <button
                type="button"
                disabled={busyProjectId === membership.projectId}
                onClick={() => handleToggleMembership(membership.projectId, membership.status)}
                className="rounded-md bg-black/10 px-3 py-1 text-xs font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {membership.status === "blocked" ? "Reativar" : "Revogar"}
              </button>
            </div>
          ))}
        </div>

        {availableProjects.length > 0 && (
          <div className="mt-4 flex items-end gap-2">
            <div className="flex-1">
              <Select
                id="addProject"
                label="Conceder acesso a"
                placeholder="Selecione um projeto"
                variant="light"
                options={availableProjects.map((p) => ({ value: p.id, label: p.name }))}
                value={addProjectId}
                onChange={(e) => setAddProjectId(e.target.value)}
              />
            </div>
            <button
              type="button"
              disabled={!addProjectId || busyProjectId === addProjectId}
              onClick={handleGrant}
              className="rounded-md bg-pmon-yellow px-4 py-2 text-sm font-semibold text-pmon-black hover:bg-pmon-yellow/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Adicionar
            </button>
          </div>
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
  );
}
