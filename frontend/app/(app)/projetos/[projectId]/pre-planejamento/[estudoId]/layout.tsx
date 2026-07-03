import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { EstudoTabs } from "@/components/pre-planejamento/EstudoTabs";
import { StudyProvider } from "@/components/pre-planejamento/StudyContext";
import { getStudy } from "@/lib/api/pre-planejamento";

// Layout do estudo: busca o estudo uma vez (services/floors/cycles/holidays)
// e repassa via StudyProvider pras 3 abas (Client Components), evitando 3
// fetches duplicados de getStudy.

interface EstudoLayoutProps {
  children: ReactNode;
  params: Promise<{ projectId: string; estudoId: string }>;
}

export default async function EstudoLayout({ children, params }: EstudoLayoutProps) {
  const { projectId, estudoId } = await params;
  const study = await getStudy(projectId, estudoId);

  if (!study) notFound();

  return (
    <StudyProvider projectId={projectId} study={study}>
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold text-black">{study.name}</h1>
        <EstudoTabs baseHref={`/projetos/${projectId}/pre-planejamento/${estudoId}`} />
        {children}
      </div>
    </StudyProvider>
  );
}
