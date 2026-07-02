import { createClient } from "@/lib/supabase/client";
import type { NewProjectInput } from "@/types/project";

// Só client-side (não importa lib/supabase/server.ts) — chamado a partir do
// NewProjectForm, que roda inteiramente no browser. owner_id não é parâmetro:
// resolvido aqui via sessão, e a RLS de projects (owner_id = auth.uid()) já
// rejeita qualquer valor divergente de qualquer forma.

async function getCurrentUserId(): Promise<string> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) throw new Error("Sessão expirada.");
  return user.id;
}

export async function uploadProjectImage(file: File): Promise<string> {
  const supabase = createClient();
  const ownerId = await getCurrentUserId();
  const path = `${ownerId}/${crypto.randomUUID()}-${file.name}`;

  const { error } = await supabase.storage.from("project-images").upload(path, file);
  if (error) throw error;

  const {
    data: { publicUrl },
  } = supabase.storage.from("project-images").getPublicUrl(path);

  return publicUrl;
}

export async function createProject(input: NewProjectInput): Promise<string> {
  const supabase = createClient();
  const ownerId = await getCurrentUserId();

  const { data, error } = await supabase
    .from("projects")
    .insert({
      owner_id: ownerId,
      name: input.name,
      client_name: input.clientName,
      city: input.city,
      state: input.state,
      tipologia_obra: input.tipologiaObra,
      tipologia_construtiva: input.tipologiaConstrutiva,
      tipologia_construtiva_outros: input.tipologiaConstrutivaOutros ?? null,
      num_torres: input.numTorres ?? null,
      num_pavimentos: input.numPavimentos ?? null,
      num_unidades: input.numUnidades ?? null,
      num_lotes: input.numLotes ?? null,
      area_construida: input.areaConstruida ?? null,
      area_privativa: input.areaPrivativa ?? null,
      orcamento: input.orcamento ?? null,
      data_base_orcamento: input.dataBaseOrcamento ?? null,
      prazo_estimado_meses: input.prazoEstimadoMeses ?? null,
      image_url: input.imageUrl ?? null,
    })
    .select("id")
    .single();

  if (error || !data) {
    throw error ?? new Error("Falha ao criar o projeto.");
  }

  return data.id;
}
