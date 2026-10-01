import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import { createClient as createClientRecord } from "@/lib/api/client-mutations";
import type { PipelineStage } from "@/types/crm";

// Só client-side (mesmo padrão de lib/api/project-mutations.ts). Sem
// transação real (Supabase REST não expõe BEGIN/COMMIT pro frontend) — se o
// insert de projects falhar depois do cliente já ter sido criado, fica um
// cliente órfão; mesmo risco não-transacional já aceito em todo o resto do
// app (ex.: upload de imagem + insert de projeto em project-mutations.ts).

interface CreateProspectInput {
  projectName: string;
  existingClientId: string | null;
  newClient: { code: string; legalName: string } | null;
}

async function getCurrentUserId(): Promise<string> {
  const supabase = createSupabaseClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) throw new Error("Sessão expirada.");
  return user.id;
}

export async function createProspect(input: CreateProspectInput): Promise<string> {
  const supabase = createSupabaseClient();
  const ownerId = await getCurrentUserId();

  let clientId = input.existingClientId;
  let clientLegalName: string | null = null;

  if (input.newClient) {
    clientId = await createClientRecord({
      code: input.newClient.code,
      legalName: input.newClient.legalName,
    });
    clientLegalName = input.newClient.legalName;
  } else if (clientId) {
    const { data } = await supabase.from("clients").select("legal_name").eq("id", clientId).single();
    clientLegalName = data?.legal_name ?? null;
  }

  const { data, error } = await supabase
    .from("projects")
    .insert({
      name: input.projectName,
      owner_id: ownerId,
      client_id: clientId,
      // client_name (texto legado, pré-client_id) também é preenchido aqui pra
      // não regredir a listagem de /projetos, que ainda lê client_name direto
      // em vez de fazer join com clients via client_id.
      client_name: clientLegalName,
      pipeline_stage: "prospect",
    })
    .select("id")
    .single();

  if (error || !data) throw error ?? new Error("Falha ao criar o prospect.");
  return data.id;
}

// .select().single() em vez de só .update() — RLS (projects_owner_access +
// projects_update_crm, ver backend/migrations/027_projects_write_crm.sql)
// filtra silenciosamente linhas que o usuário não pode escrever (0 linhas
// afetadas, sem erro de Postgres); .single() com 0 linhas retornadas *é* um
// erro do PostgREST, o que deixa esse caso detectável aqui.
export async function updateProjectStage(projectId: string, newStage: PipelineStage): Promise<void> {
  const supabase = createSupabaseClient();

  const { error } = await supabase
    .from("projects")
    .update({ pipeline_stage: newStage })
    .eq("id", projectId)
    .select("id")
    .single();

  if (error) throw new Error("Você não tem permissão para mover este projeto.");
}
