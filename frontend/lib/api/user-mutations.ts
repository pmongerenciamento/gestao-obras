import type { CreateUserInput, UserAction } from "@/types/user";
import { apiFetch } from "@/lib/api/backend-client";
import { createClient } from "@/lib/supabase/client";

// Escrita client-side (mesmo padrão de lib/api/project-mutations.ts) — quem
// chama recarrega a lista via router.refresh() depois (mesmo padrão do
// deleteProject em components/layout/ProjectCard.tsx), então as funções aqui
// não precisam devolver o User mapeado de volta.

async function getAccessToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Sessão expirada.");
  return session.access_token;
}

export async function createUser(input: CreateUserInput): Promise<void> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  await apiFetch("/api/v1/users", token, {
    method: "POST",
    body: JSON.stringify({
      email: input.email,
      full_name: input.fullName,
      project_ids: input.projectIds,
    }),
  });
}

export async function updateUser(
  userId: string,
  action: UserAction,
  projectId?: string,
): Promise<void> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  await apiFetch(`/api/v1/users/${userId}`, token, {
    method: "PATCH",
    body: JSON.stringify({ action, project_id: projectId ?? null }),
  });
}

export async function deleteUser(userId: string): Promise<void> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  await apiFetch(`/api/v1/users/${userId}`, token, { method: "DELETE" });
}

export async function grantAccess(userId: string, projectId: string): Promise<void> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  await apiFetch(`/api/v1/users/${userId}`, token, {
    method: "PATCH",
    body: JSON.stringify({ action: "grant", project_id: projectId }),
  });
}

// Upload fica sob a pasta do próprio master (dono da sessão que faz o
// upload) — a policy de storage.objects exige que o prefixo do caminho seja
// o auth.uid() de quem escreve, não o id do usuário sendo editado. A URL
// pública resultante é só um valor de texto, então funciona normalmente como
// avatar de qualquer usuário depois de gravada em profiles.avatar_url.
export async function uploadAvatar(file: File): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Sessão expirada.");

  const path = `${session.user.id}/${crypto.randomUUID()}-${file.name}`;
  const { error } = await supabase.storage.from("avatar-images").upload(path, file);
  if (error) throw error;

  const {
    data: { publicUrl },
  } = supabase.storage.from("avatar-images").getPublicUrl(path);
  return publicUrl;
}

export async function setAvatar(userId: string, avatarUrl: string): Promise<void> {
  if (!process.env.NEXT_PUBLIC_API_URL) throw new Error("Backend indisponível.");

  const token = await getAccessToken();
  await apiFetch(`/api/v1/users/${userId}`, token, {
    method: "PATCH",
    body: JSON.stringify({ action: "set_avatar", avatar_url: avatarUrl }),
  });
}
