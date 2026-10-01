import { redirect } from "next/navigation";
import { ComercialView } from "@/components/proposals/ComercialView";
import { getLatestProposal, getProjectPipelineStage, listServiceTypes } from "@/lib/api/proposals";
import { listTeams } from "@/lib/api/teams";
import { listUserModules } from "@/lib/api/modules";

// Aba Comercial: proposta mais recente do projeto (ou formulário pra criar a
// primeira) + ações de mudança de etapa do pipeline. RLS já bloqueia leitura
// de quem não tem o módulo 'crm', mas confere aqui também pra redirecionar
// graciosamente em vez de renderizar uma tela vazia/quebrada.

interface ComercialPageProps {
  params: Promise<{ projectId: string }>;
}

export default async function ComercialPage({ params }: ComercialPageProps) {
  const { projectId } = await params;

  const userModules = await listUserModules();
  if (!userModules.includes("crm")) redirect(`/projetos/${projectId}`);

  const [proposal, pipelineStage, serviceTypes, teams] = await Promise.all([
    getLatestProposal(projectId),
    getProjectPipelineStage(projectId),
    listServiceTypes(),
    listTeams(),
  ]);

  return (
    <ComercialView
      projectId={projectId}
      proposal={proposal}
      pipelineStage={pipelineStage ?? "prospect"}
      serviceTypes={serviceTypes}
      teams={teams}
    />
  );
}
