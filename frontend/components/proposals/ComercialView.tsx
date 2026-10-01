"use client";

import { useRouter } from "next/navigation";
import type { Proposal, ServiceType } from "@/types/proposal";
import type { PipelineStage } from "@/types/crm";
import type { Team } from "@/types/team";
import { NewProposalForm } from "@/components/proposals/NewProposalForm";
import { ProposalDetails } from "@/components/proposals/ProposalDetails";

interface ComercialViewProps {
  projectId: string;
  proposal: Proposal | null;
  pipelineStage: PipelineStage;
  serviceTypes: ServiceType[];
  teams: Team[];
}

export function ComercialView({
  projectId,
  proposal,
  pipelineStage,
  serviceTypes,
  teams,
}: ComercialViewProps) {
  const router = useRouter();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-black">Comercial</h1>

      {proposal ? (
        <ProposalDetails
          proposal={proposal}
          pipelineStage={pipelineStage}
          projectId={projectId}
          teams={teams}
          onUpdated={() => router.refresh()}
          onClosed={() => router.push(`/projetos/${projectId}`)}
        />
      ) : (
        <NewProposalForm
          projectId={projectId}
          serviceTypes={serviceTypes}
          onCreated={() => router.refresh()}
        />
      )}
    </div>
  );
}
