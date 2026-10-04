"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IconDots } from "@tabler/icons-react";
import type { ProjectOption, User } from "@/types/user";
import { MODULES, type AccessResult } from "@/types/access";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { NewUserModal } from "@/components/users/NewUserModal";
import { AccessModal } from "@/components/users/AccessModal";
import { ModuleTeamModal } from "@/components/users/ModuleTeamModal";
import { ONLY_MASTER_DELETE_MESSAGE, TEAM_MEMBER_DELETE_MESSAGE } from "@/lib/api/access-errors";
import { deleteUser, updateUser } from "@/lib/api/user-mutations";

// Lista de usuários da tela /usuarios — menu de três pontos por linha segue o
// mesmo padrão de components/layout/ProjectCard.tsx.

interface UserTableProps {
  users: User[];
  projects: ProjectOption[];
  access: AccessResult;
  currentUserId: string | null;
}

function statusBadge(user: User) {
  if (user.banned) return { label: "Bloqueada", className: "bg-red-100 text-red-800" };
  if (!user.emailConfirmedAt) return { label: "Convite pendente", className: "bg-yellow-100 text-yellow-800" };
  return { label: "Ativa", className: "bg-green-100 text-green-800" };
}

export function UserTable({ users, projects, access, currentUserId }: UserTableProps) {
  const router = useRouter();
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [newUserOpen, setNewUserOpen] = useState(false);
  const [accessUserId, setAccessUserId] = useState<string | null>(null);
  const [moduleTeamUserId, setModuleTeamUserId] = useState<string | null>(null);

  // Seção de módulos e times: só aparece pro master (is_master() no banco) e
  // só se getAccessData() funcionou — senão a tela segue igual, com aviso.
  const masterAccess = access.ok && access.data.isMaster ? access.data : null;
  const moduleTeamUser = users.find((u) => u.id === moduleTeamUserId) ?? null;

  // Exclusão bloqueada antes de chamar o backend: o trigger da 043 impede
  // apagar o único master (a Admin API devolveria um erro genérico), e
  // team_members.profile_id não tem on delete cascade (015).
  function deleteBlockReason(user: User): string | null {
    if (!masterAccess) return null;
    const profile = masterAccess.profiles[user.id];
    if (!profile) return null;
    if (profile.systemRole === "master") {
      const otherMaster = Object.values(masterAccess.profiles).some(
        (p) => p.profileId !== user.id && p.systemRole === "master",
      );
      if (!otherMaster) return ONLY_MASTER_DELETE_MESSAGE;
    }
    if (profile.teams.length > 0) return TEAM_MEMBER_DELETE_MESSAGE;
    return null;
  }
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Derivado do prop users (não guardado no state) pra sempre refletir os
  // dados mais recentes depois de um router.refresh() — se fosse state
  // próprio, ficaria "congelado" com os dados de quando o modal abriu.
  const accessUser = users.find((u) => u.id === accessUserId) ?? null;

  async function handleToggleBan(user: User) {
    setMenuOpenId(null);
    setActionError(null);
    try {
      await updateUser(user.id, user.banned ? "unblock" : "block");
      router.refresh();
    } catch {
      setActionError("Não foi possível atualizar o usuário. Tente novamente.");
    }
  }

  async function handleResetPassword(user: User) {
    setMenuOpenId(null);
    setActionError(null);
    try {
      await updateUser(user.id, "reset_password");
    } catch {
      setActionError("Não foi possível enviar o e-mail de redefinição. Tente novamente.");
    }
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) return;
    const blockReason = deleteBlockReason(deleteTarget);
    if (blockReason) {
      setDeleteError(blockReason);
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteUser(deleteTarget.id);
      router.refresh();
      setDeleteTarget(null);
    } catch {
      setDeleteError("Não foi possível excluir o usuário. Tente novamente.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-black">Usuários</h1>
        <Button onClick={() => setNewUserOpen(true)}>Novo usuário</Button>
      </div>

      {actionError && <p className="mb-4 text-sm text-red-500">{actionError}</p>}
      {!access.ok && (
        <p className="mb-4 rounded-md bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
          Módulos e times: {access.error}
        </p>
      )}

      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="rounded-t-lg border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="rounded-tl-lg px-4 py-3 font-medium">Usuário</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Projetos</th>
              {masterAccess && <th className="px-4 py-3 font-medium">Módulos</th>}
              {masterAccess && <th className="px-4 py-3 font-medium">Time</th>}
              <th className="rounded-tr-lg px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const badge = statusBadge(user);
              return (
                <tr key={user.id} className="border-b border-black/5 last:border-0">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-pmon-black text-xs font-semibold text-white">
                        {(user.fullName ?? user.email).charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-medium text-black">{user.fullName ?? "—"}</p>
                        <p className="text-xs text-black/50">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-black/70">{user.memberships.length}</td>
                  {masterAccess && (
                    <td className="px-4 py-3 text-black/70">
                      {masterAccess.profiles[user.id]
                        ? MODULES.filter((m) => masterAccess.profiles[user.id].modules.includes(m.code))
                            .map((m) => m.label)
                            .join(", ") || "—"
                        : "sem perfil"}
                    </td>
                  )}
                  {masterAccess && (
                    <td className="px-4 py-3 text-black/70">
                      {masterAccess.profiles[user.id]?.teams
                        .map((t) => masterAccess.teams.find((team) => team.id === t.teamId)?.name ?? "?")
                        .join(", ") || "—"}
                    </td>
                  )}
                  <td className="relative px-4 py-3 text-right">
                    <div
                      className="relative inline-block"
                      onBlur={(e) => {
                        if (!e.currentTarget.contains(e.relatedTarget)) setMenuOpenId(null);
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => setMenuOpenId(menuOpenId === user.id ? null : user.id)}
                        className="flex h-7 w-7 items-center justify-center rounded-full text-black/50 hover:bg-black/5"
                      >
                        <IconDots size={16} />
                      </button>
                      {menuOpenId === user.id && (
                        <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded-md border border-black/10 bg-white py-1 shadow-lg">
                          <button
                            type="button"
                            onClick={() => {
                              setMenuOpenId(null);
                              setAccessUserId(user.id);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-black hover:bg-black/5"
                          >
                            Gerenciar acesso
                          </button>
                          {masterAccess && (
                            <button
                              type="button"
                              onClick={() => {
                                setMenuOpenId(null);
                                setModuleTeamUserId(user.id);
                              }}
                              className="w-full px-3 py-2 text-left text-sm text-black hover:bg-black/5"
                            >
                              Módulos e time
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleResetPassword(user)}
                            className="w-full px-3 py-2 text-left text-sm text-black hover:bg-black/5"
                          >
                            Resetar senha
                          </button>
                          <button
                            type="button"
                            onClick={() => handleToggleBan(user)}
                            className="w-full px-3 py-2 text-left text-sm text-black hover:bg-black/5"
                          >
                            {user.banned ? "Desbloquear conta" : "Bloquear conta"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setMenuOpenId(null);
                              setDeleteTarget(user);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                          >
                            Excluir usuário
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-black/50">Nenhum usuário cadastrado ainda.</p>
        )}
      </div>

      <NewUserModal
        open={newUserOpen}
        projects={projects}
        onClose={() => setNewUserOpen(false)}
        onCreated={() => {
          setNewUserOpen(false);
          router.refresh();
        }}
      />

      {accessUser && (
        <AccessModal
          user={accessUser}
          projects={projects}
          onClose={() => setAccessUserId(null)}
          onChanged={() => router.refresh()}
        />
      )}

      {masterAccess && moduleTeamUser && (
        <ModuleTeamModal
          user={moduleTeamUser}
          access={masterAccess.profiles[moduleTeamUser.id]}
          teams={masterAccess.teams}
          isSelf={moduleTeamUser.id === currentUserId}
          onClose={() => setModuleTeamUserId(null)}
          onChanged={() => router.refresh()}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir usuário"
        description={`Tem certeza que deseja excluir ${deleteTarget?.fullName ?? deleteTarget?.email}? Esta ação não pode ser desfeita.`}
        confirmLabel="Excluir"
        loadingLabel="Excluindo..."
        isLoading={deleting}
        error={deleteError}
        onConfirm={handleConfirmDelete}
        onCancel={() => {
          setDeleteTarget(null);
          setDeleteError(null);
        }}
      />
    </>
  );
}
