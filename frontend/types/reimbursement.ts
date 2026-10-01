// Espelha backend/migrations/030_create_reimbursements.sql
export type ReimbursementReportStatus = "rascunho" | "enviado" | "aprovado" | "rejeitado";

export type ReimbursementItemType =
  | "deslocamento_escritorio"
  | "visita_cliente"
  | "visita_comercial"
  | "alimentacao"
  | "outros";

export type RateRuleUnit = "por_km" | "valor_fixo_diario";

export interface CostCenter {
  id: string;
  name: string;
}

export interface RateRule {
  id: string;
  type: ReimbursementItemType;
  value: number;
  unit: RateRuleUnit;
  effectiveStartDate: string;
  effectiveEndDate: string | null;
}

export interface ReimbursementReport {
  id: string;
  profileId: string;
  periodStart: string;
  periodEnd: string;
  status: ReimbursementReportStatus;
  rejectionReason: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ReimbursementItem {
  id: string;
  reportId: string;
  type: ReimbursementItemType;
  projectId: string | null;
  projectName: string | null;
  costCenterId: string | null;
  costCenterName: string | null;
  expenseDate: string;
  description: string;
  kmTraveled: number | null;
  kmRate: number | null;
  tollAmount: number;
  otherAmount: number;
  requiresPreapproval: boolean;
  totalAmount: number;
}

export interface ProjectOption {
  id: string;
  name: string;
}

export interface NewReportInput {
  periodStart: string;
  periodEnd: string;
}

export interface NewItemInput {
  type: ReimbursementItemType;
  projectId?: string;
  costCenterId?: string;
  expenseDate: string;
  description: string;
  kmTraveled?: number;
  kmRate?: number;
  tollAmount?: number;
  otherAmount?: number;
  requiresPreapproval: boolean;
  totalAmount: number;
}
