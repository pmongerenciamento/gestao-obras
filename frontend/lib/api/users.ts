import type { MembershipStatus, User } from "@/types/user";
import { apiFetch } from "@/lib/api/backend-client";
import { createClient } from "@/lib/supabase/server";

// Leitura server-side (sessão via cookie), mesmo padrão de lib/api/projects.ts.
// Escrita (criar/bloquear/excluir) fica em lib/api/user-mutations.ts, que roda
// client-side — mesma separação de lib/api/project-mutations.ts.

interface RawMembership {
  project_id: string;
  project_name: string;
  status: MembershipStatus;
}

interface RawUser {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  created_at: string;
  email_confirmed_at: string | null;
  banned: boolean;
  memberships: RawMembership[];
}

export function mapUser(raw: RawUser): User {
  return {
    id: raw.id,
    email: raw.email,
    fullName: raw.full_name,
    avatarUrl: raw.avatar_url,
    createdAt: raw.created_at,
    emailConfirmedAt: raw.email_confirmed_at,
    banned: raw.banned,
    memberships: raw.memberships.map((m) => ({
      projectId: m.project_id,
      projectName: m.project_name,
      status: m.status,
    })),
  };
}

export async function listUsers(): Promise<User[]> {
  if (!process.env.NEXT_PUBLIC_API_URL) return [];

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return [];

  const raw = await apiFetch<RawUser[]>("/api/v1/users", session.access_token);
  return raw.map(mapUser);
}
