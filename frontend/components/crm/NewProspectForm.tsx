"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { createProspect } from "@/lib/api/pipeline-mutations";
import type { Client } from "@/types/client";

const NEW_CLIENT_VALUE = "__new__";

const formSchema = z
  .object({
    clientId: z.string().min(1, "Selecione um cliente"),
    projectName: z.string().min(1, "Obrigatório"),
    newClientCode: z.string().optional(),
    newClientLegalName: z.string().optional(),
  })
  .superRefine((values, ctx) => {
    if (values.clientId !== NEW_CLIENT_VALUE) return;
    if (!values.newClientCode || !/^\d{3}$/.test(values.newClientCode)) {
      ctx.addIssue({
        code: "custom",
        path: ["newClientCode"],
        message: "Código deve ter exatamente 3 dígitos",
      });
    }
    if (!values.newClientLegalName) {
      ctx.addIssue({ code: "custom", path: ["newClientLegalName"], message: "Obrigatório" });
    }
  });

type FormValues = z.infer<typeof formSchema>;

interface NewProspectFormProps {
  clients: Client[];
  suggestedClientCode: string;
  onCreated: () => void;
}

export function NewProspectForm({ clients, suggestedClientCode, onCreated }: NewProspectFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema), defaultValues: { clientId: "" } });

  const clientId = watch("clientId");
  const isNewClient = clientId === NEW_CLIENT_VALUE;

  // Pré-preenche o código sugerido ao entrar em "criar novo cliente" — o
  // campo continua editável (register normal), isto só define o valor
  // inicial. Reaparece a cada vez que o select volta pra essa opção.
  useEffect(() => {
    if (isNewClient) {
      setValue("newClientCode", suggestedClientCode);
    }
  }, [isNewClient, suggestedClientCode, setValue]);

  const clientOptions = [
    ...clients.map((c) => ({ value: c.id, label: `${c.code} — ${c.legalName}` })),
    { value: NEW_CLIENT_VALUE, label: "+ Criar novo cliente" },
  ];

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createProspect({
        projectName: values.projectName,
        existingClientId: isNewClient ? null : values.clientId,
        newClient: isNewClient
          ? { code: values.newClientCode!, legalName: values.newClientLegalName! }
          : null,
      });
      onCreated();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível criar o prospect. Tente novamente.",
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
        <Select
          id="clientId"
          label="Cliente"
          variant="light"
          placeholder="Selecione..."
          options={clientOptions}
          error={errors.clientId?.message}
          {...register("clientId")}
        />
        <Input
          id="projectName"
          label="Nome do projeto"
          variant="light"
          error={errors.projectName?.message}
          {...register("projectName")}
        />
      </div>

      {isNewClient && (
        <div className="grid grid-cols-2 gap-4 rounded-md border border-dashed border-black/20 p-4">
          <Input
            id="newClientCode"
            label="Código do cliente (3 dígitos)"
            variant="light"
            maxLength={3}
            error={errors.newClientCode?.message}
            {...register("newClientCode")}
          />
          <Input
            id="newClientLegalName"
            label="Nome do cliente"
            variant="light"
            error={errors.newClientLegalName?.message}
            {...register("newClientLegalName")}
          />
        </div>
      )}

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-fit">
        {submitting ? "Criando..." : "Criar prospect"}
      </Button>
    </form>
  );
}
