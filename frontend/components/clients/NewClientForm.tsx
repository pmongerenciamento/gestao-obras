"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { createClient } from "@/lib/api/client-mutations";

const formSchema = z.object({
  code: z.string().regex(/^\d{3}$/, "Código deve ter exatamente 3 dígitos"),
  legalName: z.string().min(1, "Obrigatório"),
  contactName: z.string().optional(),
  contactEmail: z.string().email("E-mail inválido").optional().or(z.literal("")),
  contactPhone: z.string().optional(),
  notes: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

interface NewClientFormProps {
  onCreated: () => void;
}

export function NewClientForm({ onCreated }: NewClientFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema) });

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createClient({
        code: values.code,
        legalName: values.legalName,
        contactName: values.contactName,
        contactEmail: values.contactEmail,
        contactPhone: values.contactPhone,
        notes: values.notes,
      });
      onCreated();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível salvar o cliente. Tente novamente.",
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="mb-6 flex flex-col gap-4 rounded-lg border border-black/10 bg-white p-6"
    >
      <div className="grid grid-cols-2 gap-4">
        <Input
          id="code"
          label="Código (3 dígitos)"
          variant="light"
          maxLength={3}
          error={errors.code?.message}
          {...register("code")}
        />
        <Input
          id="legalName"
          label="Nome"
          variant="light"
          error={errors.legalName?.message}
          {...register("legalName")}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Input
          id="contactName"
          label="Contato"
          variant="light"
          error={errors.contactName?.message}
          {...register("contactName")}
        />
        <Input
          id="contactEmail"
          label="E-mail"
          type="email"
          variant="light"
          error={errors.contactEmail?.message}
          {...register("contactEmail")}
        />
      </div>
      <Input
        id="contactPhone"
        label="Telefone"
        variant="light"
        error={errors.contactPhone?.message}
        {...register("contactPhone")}
      />
      <div className="flex flex-col gap-1">
        <label htmlFor="notes" className="text-sm text-black/70">
          Observações
        </label>
        <textarea
          id="notes"
          rows={3}
          className="rounded-md border border-black/20 bg-white px-3 py-2 text-black placeholder:text-black/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow"
          {...register("notes")}
        />
      </div>

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-fit">
        {submitting ? "Salvando..." : "Salvar cliente"}
      </Button>
    </form>
  );
}
