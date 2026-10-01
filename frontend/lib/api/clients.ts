import type { Client } from "@/types/client";
import { createClient as createSupabaseServerClient } from "@/lib/supabase/server";

// Leitura real da tabela `clients` (backend/migrations/011_create_clients.sql).
// Sem RLS nessa tabela ainda (gap conhecido, ver docs/sessao-atual.md) — a
// tabela não é dona de ninguém (owner_id), é cadastro compartilhado por toda
// a equipe PMON, então o corte por usuário não se aplica aqui.

interface ClientRow {
  id: string;
  code: string;
  legal_name: string;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string | null;
}

function mapRow(row: ClientRow): Client {
  return {
    id: row.id,
    code: row.code,
    legalName: row.legal_name,
    contactName: row.contact_name,
    contactEmail: row.contact_email,
    contactPhone: row.contact_phone,
    notes: row.notes,
  };
}

export async function listClients(): Promise<Client[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("clients")
    .select("id, code, legal_name, contact_name, contact_email, contact_phone, notes")
    .order("code", { ascending: true });

  if (error || !data) return [];
  return data.map(mapRow);
}

// Sugestão de próximo código pro form de "novo cliente" (ex.: NewProspectForm).
// Filtra em JS, não em SQL: `code` aceita valores não-numéricos (ex.: "C01",
// "C02", já existentes em dados reais), então um `order by code desc` puro
// ordenaria como string e pegaria um código alfanumérico como "maior" em vez
// do maior código numérico de fato. Só uma sugestão pré-preenchida e editável
// no form — colisão de concorrência (dois prospects criados quase juntos) já
// cai no tratamento de unique_violation que a mutação de criar cliente já tem.
export async function getNextClientCode(): Promise<string> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("clients").select("code");

  if (error || !data) return "001";

  const numericCodes = data
    .map((row) => row.code as string)
    .filter((code) => /^\d+$/.test(code))
    .map(Number);

  if (numericCodes.length === 0) return "001";

  return String(Math.max(...numericCodes) + 1).padStart(3, "0");
}
