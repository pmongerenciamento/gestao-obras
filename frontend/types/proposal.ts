// Espelha backend/migrations/022_create_proposals.sql
export type ProposalStatus = "rascunho" | "enviada" | "em_negociacao" | "aceita" | "recusada";
export type PaymentType = "mensal_recorrente" | "parcela_unica" | "parcelado";

export interface ServiceType {
  id: string;
  code: string;
  name: string;
}

export interface Proposal {
  id: string;
  projectId: string;
  version: number;
  serviceTypeId: string | null;
  serviceTypeName: string | null;
  value: number;
  paymentType: PaymentType;
  installmentsCount: number | null;
  scopeDescription: string | null;
  status: ProposalStatus;
  validUntil: string | null;
  lostReason: string | null;
}

export interface NewProposalInput {
  serviceTypeId: string;
  value: number;
  paymentType: PaymentType;
  installmentsCount?: number;
  scopeDescription?: string;
  validUntil?: string;
}
