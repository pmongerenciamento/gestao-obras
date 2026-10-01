"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { closeDeal } from "@/lib/api/close-deal-mutations";
import type { Team } from "@/types/team";

const formSchema = z.object({
  clientLegalName: z.string().min(1, "Obrigatório"),
  clientCnpj: z.string().min(1, "Obrigatório"),
  clientAddress: z.string().min(1, "Obrigatório"),
  legalRepName: z.string().min(1, "Obrigatório"),
  legalRepCpf: z.string().min(1, "Obrigatório"),
  legalRepRole: z.string().min(1, "Obrigatório"),
  speLegalName: z.string().min(1, "Obrigatório"),
  speCnpj: z.string().min(1, "Obrigatório"),
  speAddress: z.string().min(1, "Obrigatório"),
  teamId: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

interface CloseDealFormProps {
  projectId: string;
  teams: Team[];
  onClosed: () => void;
  onCancel: () => void;
}

export function CloseDealForm({ projectId, teams, onClosed, onCancel }: CloseDealFormProps) {
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
      await closeDeal({
        projectId,
        clientLegalName: values.clientLegalName,
        clientCnpj: values.clientCnpj,
        clientAddress: values.clientAddress,
        legalRepName: values.legalRepName,
        legalRepCpf: values.legalRepCpf,
        legalRepRole: values.legalRepRole,
        speLegalName: values.speLegalName,
        speCnpj: values.speCnpj,
        speAddress: values.speAddress,
        teamId: values.teamId || null,
      });
      onClosed();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível fechar o negócio. Tente novamente.",
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6 rounded-lg border border-black/10 bg-white p-6"
    >
      <div>
        <h3 className="mb-3 text-sm font-semibold text-black/70">Dados jurídicos do cliente</h3>
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="clientLegalName"
            label="Razão social"
            variant="light"
            error={errors.clientLegalName?.message}
            {...register("clientLegalName")}
          />
          <Input
            id="clientCnpj"
            label="CNPJ"
            variant="light"
            error={errors.clientCnpj?.message}
            {...register("clientCnpj")}
          />
        </div>
        <div className="mt-4">
          <Input
            id="clientAddress"
            label="Endereço"
            variant="light"
            error={errors.clientAddress?.message}
            {...register("clientAddress")}
          />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-4">
          <Input
            id="legalRepName"
            label="Representante legal"
            variant="light"
            error={errors.legalRepName?.message}
            {...register("legalRepName")}
          />
          <Input
            id="legalRepCpf"
            label="CPF"
            variant="light"
            error={errors.legalRepCpf?.message}
            {...register("legalRepCpf")}
          />
          <Input
            id="legalRepRole"
            label="Cargo"
            variant="light"
            error={errors.legalRepRole?.message}
            {...register("legalRepRole")}
          />
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-black/70">SPE</h3>
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="speLegalName"
            label="Razão social"
            variant="light"
            error={errors.speLegalName?.message}
            {...register("speLegalName")}
          />
          <Input
            id="speCnpj"
            label="CNPJ"
            variant="light"
            error={errors.speCnpj?.message}
            {...register("speCnpj")}
          />
        </div>
        <div className="mt-4">
          <Input
            id="speAddress"
            label="Endereço"
            variant="light"
            error={errors.speAddress?.message}
            {...register("speAddress")}
          />
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-black/70">Time responsável</h3>
        <Select
          id="teamId"
          label="Time"
          variant="light"
          placeholder="Nenhum"
          options={teams.map((t) => ({ value: t.id, label: t.name }))}
          error={errors.teamId?.message}
          {...register("teamId")}
        />
      </div>

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" isLoading={submitting}>
          {submitting ? "Fechando..." : "Confirmar fechamento"}
        </Button>
        <button
          type="button"
          disabled={submitting}
          onClick={onCancel}
          className="text-sm text-black/50 hover:text-black/70"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
