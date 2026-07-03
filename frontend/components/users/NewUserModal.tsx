"use client";

import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { ProjectOption } from "@/types/user";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { createUser } from "@/lib/api/user-mutations";

// Modal de convite de novo usuário — mesmo padrão visual de overlay do
// components/ui/ConfirmDialog.tsx. Precisa de ao menos 1 projeto selecionado
// porque project_members.project_id não é nulo (backend/migrations/005).

const formSchema = z.object({
  email: z.string().email("E-mail inválido"),
  fullName: z.string().min(1, "Obrigatório"),
  projectIds: z.array(z.string()).min(1, "Selecione ao menos um projeto"),
});

type FormValues = z.infer<typeof formSchema>;

interface NewUserModalProps {
  open: boolean;
  projects: ProjectOption[];
  onClose: () => void;
  onCreated: () => void;
}

export function NewUserModal({ open, projects, onClose, onCreated }: NewUserModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: "", fullName: "", projectIds: [] },
  });

  if (!open) return null;

  function handleClose() {
    reset();
    setSubmitError(null);
    onClose();
  }

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createUser(values);
      reset();
      onCreated();
    } catch {
      setSubmitError("Não foi possível criar o usuário. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-black">Novo usuário</h2>
        <p className="mt-1 text-sm text-black/60">
          Um convite por e-mail será enviado pra essa pessoa definir a própria senha.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4">
          <Input
            id="email"
            label="E-mail"
            type="email"
            variant="light"
            error={errors.email?.message}
            {...register("email")}
          />
          <Input
            id="fullName"
            label="Nome completo"
            variant="light"
            error={errors.fullName?.message}
            {...register("fullName")}
          />

          <Controller
            control={control}
            name="projectIds"
            render={({ field }) => (
              <div className="flex flex-col gap-1">
                <span className="text-sm text-black/70">Projetos com acesso</span>
                <div className="flex max-h-40 flex-col gap-2 overflow-y-auto rounded-md border border-black/20 p-3">
                  {projects.length === 0 && (
                    <p className="text-sm text-black/40">Nenhum projeto cadastrado ainda.</p>
                  )}
                  {projects.map((project) => (
                    <label key={project.id} className="flex items-center gap-2 text-sm text-black">
                      <input
                        type="checkbox"
                        checked={field.value.includes(project.id)}
                        onChange={(e) => {
                          field.onChange(
                            e.target.checked
                              ? [...field.value, project.id]
                              : field.value.filter((id) => id !== project.id),
                          );
                        }}
                      />
                      {project.name}
                    </label>
                  ))}
                </div>
                {errors.projectIds?.message && (
                  <p className="text-sm text-red-500">{errors.projectIds.message}</p>
                )}
              </div>
            )}
          />

          {submitError && <p className="text-sm text-red-500">{submitError}</p>}

          <div className="mt-2 flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              disabled={submitting}
              className="rounded-md bg-black/10 px-4 py-2 text-sm font-medium text-black hover:bg-black/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancelar
            </button>
            <Button type="submit" isLoading={submitting}>
              {submitting ? "Enviando convite..." : "Enviar convite"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
