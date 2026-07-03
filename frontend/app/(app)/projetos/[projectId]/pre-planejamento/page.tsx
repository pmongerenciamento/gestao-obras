import { StudiesList } from "@/components/pre-planejamento/StudiesList";
import { listStudies } from "@/lib/api/pre-planejamento";

// Lista de cenários/estudos de Pré-planejamento do projeto + "+ Novo cenário"

interface PrePlanejamentoPageProps {
  params: Promise<{ projectId: string }>;
}

export default async function PrePlanejamentoPage({ params }: PrePlanejamentoPageProps) {
  const { projectId } = await params;
  const studies = await listStudies(projectId);

  return <StudiesList projectId={projectId} studies={studies} />;
}
