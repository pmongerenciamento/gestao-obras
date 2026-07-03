"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { StudyDetail } from "@/types/pre-planejamento";

// Compartilha o estudo já carregado pelo layout.tsx (Server Component) entre
// as 3 abas (Client Components), evitando 3 fetches duplicados de getStudy.

interface StudyContextValue {
  projectId: string;
  study: StudyDetail;
}

const StudyContext = createContext<StudyContextValue | null>(null);

export function StudyProvider({
  projectId,
  study,
  children,
}: StudyContextValue & { children: ReactNode }) {
  return <StudyContext.Provider value={{ projectId, study }}>{children}</StudyContext.Provider>;
}

export function useStudy(): StudyContextValue {
  const value = useContext(StudyContext);
  if (!value) throw new Error("useStudy precisa estar dentro de um StudyProvider");
  return value;
}
