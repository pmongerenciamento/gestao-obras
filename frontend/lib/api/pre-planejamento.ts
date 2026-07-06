import type { Study, StudyDetail } from "@/types/pre-planejamento";
import { fetchStudies, fetchStudyDetail } from "@/lib/api/pre-planejamento-queries";
import { createClient } from "@/lib/supabase/server";

// Leitura server-side direto no Supabase (RLS de sim_studies e afins cobre
// "é dono do projeto?", mesmo padrão de lib/api/projects.ts) — não depende
// mais do backend FastAPI. Escrita fica em lib/api/pre-planejamento-mutations.ts,
// já toda migrada pra Supabase direto também.

export async function listStudies(projectId: string): Promise<Study[]> {
  const supabase = await createClient();
  return fetchStudies(supabase, projectId);
}

export async function getStudy(projectId: string, estudoId: string): Promise<StudyDetail | null> {
  const supabase = await createClient();
  return fetchStudyDetail(supabase, projectId, estudoId);
}
