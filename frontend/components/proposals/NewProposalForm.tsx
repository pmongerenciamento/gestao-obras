"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { createProposal } from "@/lib/api/proposal-mutations";
import type { ServiceType } from "@/types/proposal";

const PAYMENT_TYPE_OPTIONS = [
  { value: "mensal_recorrente", label: "Mensal recorrente" },
  { value: "parcela_unica", label: "Parcela única" },
  { value: "parcelado", label: "Parcelado" },
];

// z.coerce faz o schema de entrada (string vinda de <input type="number">
// não controlado) divergir do de saída (já coagido pro número) — mesmo
// atrito de tipos resolvido em NewProjectForm.tsx, mesma solução aqui.
const emptyToUndefined = (val: unknown) => (val === "" ? undefined : val);
const optionalInt = z.preprocess(emptyToUndefined, z.coerce.number().int().positive().optional());

const formSchema = z
  .object({
    serviceTypeId: z.string().min(1, "Selecione um tipo de serviço"),
    value: z.coerce.number().positive("Deve ser maior que zero"),
    paymentType: z.enum(["mensal_recorrente", "parcela_unica", "parcelado"], {
      message: "Selecione a forma de pagamento",
    }),
    installmentsCount: optionalInt,
    scopeDescription: z.string().optional(),
    validUntil: z.string().optional(),
  })
  .superRefine((values, ctx) => {
    if (values.paymentType === "parcelado" && !values.installmentsCount) {
      ctx.addIssue({
        code: "custom",
        path: ["installmentsCount"],
        message: "Informe o número de parcelas",
      });
    }
  });

type FormInput = z.input<typeof formSchema>;
type FormOutput = z.output<typeof formSchema>;

interface NewProposalFormProps {
  projectId: string;
  serviceTypes: ServiceType[];
  onCreated: () => void;
}

export function NewProposalForm({ projectId, serviceTypes, onCreated }: NewProposalFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormInput, unknown, FormOutput>({ resolver: zodResolver(formSchema) });

  const paymentType = watch("paymentType");

  async function onSubmit(values: FormOutput) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createProposal(projectId, {
        serviceTypeId: values.serviceTypeId,
        value: values.value,
        paymentType: values.paymentType,
        installmentsCount: values.installmentsCount,
        scopeDescription: values.scopeDescription,
        validUntil: values.validUntil,
      });
      onCreated();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível criar a proposta. Tente novamente.",
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-4 rounded-lg border border-black/10 bg-white p-6"
    >
      <p className="text-sm text-black/60">
        Nenhuma proposta criada ainda para este projeto. Preencha os dados abaixo para criar a primeira.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <Select
          id="serviceTypeId"
          label="Tipo de serviço"
          variant="light"
          placeholder="Selecione..."
          options={serviceTypes.map((st) => ({ value: st.id, label: `${st.code} — ${st.name}` }))}
          error={errors.serviceTypeId?.message}
          {...register("serviceTypeId")}
        />
        <Input
          id="value"
          label="Valor (R$)"
          type="number"
          step="0.01"
          variant="light"
          error={errors.value?.message}
          {...register("value")}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Select
          id="paymentType"
          label="Forma de pagamento"
          variant="light"
          placeholder="Selecione..."
          options={PAYMENT_TYPE_OPTIONS}
          error={errors.paymentType?.message}
          {...register("paymentType")}
        />
        {paymentType === "parcelado" && (
          <Input
            id="installmentsCount"
            label="Número de parcelas"
            type="number"
            variant="light"
            error={errors.installmentsCount?.message}
            {...register("installmentsCount")}
          />
        )}
      </div>

      <Input
        id="validUntil"
        label="Válida até"
        type="date"
        variant="light"
        error={errors.validUntil?.message}
        {...register("validUntil")}
      />

      <div className="flex flex-col gap-1">
        <label htmlFor="scopeDescription" className="text-sm text-black/70">
          Descrição do escopo
        </label>
        <textarea
          id="scopeDescription"
          rows={3}
          className="rounded-md border border-black/20 bg-white px-3 py-2 text-black placeholder:text-black/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow"
          {...register("scopeDescription")}
        />
      </div>

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-fit">
        {submitting ? "Criando..." : "Criar proposta"}
      </Button>
    </form>
  );
}
