import type { Study, StudyDetail } from "@/types/pre-planejamento";
import { apiFetch } from "@/lib/api/backend-client";
import { mapStudy, mapStudyDetail, type RawStudy, type RawStudyDetail } from "@/lib/api/pre-planejamento-mappers";
import { createClient } from "@/lib/supabase/server";

// Leitura server-side (sessão via cookie), mesmo padrão de lib/api/users.ts.
// Escrita fica em lib/api/pre-planejamento-mutations.ts (client-side), mesma
// separação de user-mutations.ts.

async function getAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

export async function listStudies(projectId: string): Promise<Study[]> {
  if (!process.env.NEXT_PUBLIC_API_URL) return [];

  const token = await getAccessToken();
  if (!token) return [];
  const raw = await apiFetch<RawStudy[]>(`/api/v1/pre-planejamento/${projectId}/estudos`, token);
  return raw.map(mapStudy);
}

export async function getStudy(projectId: string, estudoId: string): Promise<StudyDetail | null> {
  if (!process.env.NEXT_PUBLIC_API_URL) return null;

  const token = await getAccessToken();
  if (!token) return null;
  try {
    const raw = await apiFetch<RawStudyDetail>(
      `/api/v1/pre-planejamento/${projectId}/estudos/${estudoId}`,
      token,
    );
    return mapStudyDetail(raw);
  } catch {
    return null;
  }
}
