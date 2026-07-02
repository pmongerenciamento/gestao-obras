import { Header } from "@/components/layout/Header";
import { NewProjectForm } from "@/components/projects/NewProjectForm";
import { createClient } from "@/lib/supabase/server";

// Cadastro de novo projeto: identificação, tipologia, métricas, orçamento e imagem

export default async function NewProjectPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <>
      <Header
        breadcrumb={[{ label: "Projetos", href: "/" }, { label: "Novo projeto" }]}
        userEmail={user?.email}
      />
      <NewProjectForm />
    </>
  );
}
