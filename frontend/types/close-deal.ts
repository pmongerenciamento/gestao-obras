export interface CloseDealInput {
  projectId: string;
  clientLegalName: string;
  clientCnpj: string;
  clientAddress: string;
  legalRepName: string;
  legalRepCpf: string;
  legalRepRole: string;
  speLegalName: string;
  speCnpj: string;
  speAddress: string;
  teamId: string | null;
}
