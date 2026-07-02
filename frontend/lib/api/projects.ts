import type { ProjectDetail, ProjectSummary } from "@/types/project";
import { createClient } from "@/lib/supabase/server";

// Leitura real da tabela `projects` (RLS de backend/migrations/001_initial_schema.sql
// garante owner_id = auth.uid()). Um projeto recém-criado por este formulário nunca foi
// importado ainda, então status/membros/datas de snapshot não têm de onde vir de verdade —
// os defaults abaixo refletem isso (não são mock, são o estado real de "nunca importado").
// TODO: status e membros viram reais quando o backend tiver esses conceitos (ver
// lib/auth/roles.ts); lastSnapshotAt/startDate/baselineFinish/forecastFinish viram reais
// quando a importação de cronograma for ligada ao frontend.

interface ProjectRow {
  id: string;
  name: string;
  client_name: string | null;
  city: string | null;
  image_url: string | null;
}

function mapRow(row: ProjectRow, owner: { id: string; email: string | undefined } | undefined): ProjectDetail {
  return {
    id: row.id,
    name: row.name,
    clientName: row.client_name ?? "",
    city: row.city ?? "",
    imageUrl: row.image_url,
    lastSnapshotAt: null,
    status: "em_andamento",
    members: owner?.email ? [{ id: owner.id, name: owner.email }] : [],
    startDate: null,
    baselineFinish: null,
    forecastFinish: null,
  };
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data, error } = await supabase
    .from("projects")
    .select("id, name, client_name, city, image_url")
    .order("created_at", { ascending: false });

  if (error || !data) return [];

  const owner = user ? { id: user.id, email: user.email } : undefined;
  return data.map((row) => mapRow(row, owner));
}

export async function getProject(id: string): Promise<ProjectDetail | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data, error } = await supabase
    .from("projects")
    .select("id, name, client_name, city, image_url")
    .eq("id", id)
    .maybeSingle();

  if (error || !data) return null;

  const owner = user ? { id: user.id, email: user.email } : undefined;
  return mapRow(data, owner);
}
