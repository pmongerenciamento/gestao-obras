// Espelha backend/migrations/011_create_clients.sql
export interface Client {
  id: string;
  code: string;
  legalName: string;
  contactName: string | null;
  contactEmail: string | null;
  contactPhone: string | null;
  notes: string | null;
}

export interface NewClientInput {
  code: string;
  legalName: string;
  contactName?: string;
  contactEmail?: string;
  contactPhone?: string;
  notes?: string;
}
