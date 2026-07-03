// Chamada autenticada ao backend FastAPI (NEXT_PUBLIC_API_URL) — primeira
// vez que o frontend fala com o backend em vez de ir direto no Supabase (ver
// lib/api/projects.ts / project-mutations.ts). Quem resolve o access_token
// (via createClient() do browser ou do server) é o chamador; esta função só
// monta a requisição e trata erro.

export class BackendApiError extends Error {}

export async function apiFetch<T>(
  path: string,
  accessToken: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new BackendApiError(body?.detail ?? `Erro ${response.status} ao chamar o backend`);
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}
