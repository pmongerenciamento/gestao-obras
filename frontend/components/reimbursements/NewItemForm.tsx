"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { createItem } from "@/lib/api/reimbursement-mutations";
import type { CostCenter, ProjectOption, RateRule, ReimbursementItemType } from "@/types/reimbursement";

const TYPE_OPTIONS: { value: ReimbursementItemType; label: string }[] = [
  { value: "deslocamento_escritorio", label: "Deslocamento Escritório" },
  { value: "visita_cliente", label: "Visita a Cliente" },
  { value: "visita_comercial", label: "Visita Comercial" },
  { value: "alimentacao", label: "Alimentação" },
  { value: "outros", label: "Outros" },
];

const KM_TYPES: ReimbursementItemType[] = ["deslocamento_escritorio", "visita_cliente", "visita_comercial"];
const PROJECT_TYPES: ReimbursementItemType[] = ["visita_cliente", "visita_comercial"];

function rateKeyFor(type: ReimbursementItemType): ReimbursementItemType | null {
  if (type === "visita_comercial") return "visita_cliente";
  if (type === "deslocamento_escritorio" || type === "visita_cliente" || type === "alimentacao") return type;
  return null;
}

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

const emptyToUndefined = (val: unknown) => (val === "" ? undefined : val);
const optionalNumber = z.preprocess(emptyToUndefined, z.coerce.number().optional());

const formSchema = z
  .object({
    type: z.enum(["deslocamento_escritorio", "visita_cliente", "visita_comercial", "alimentacao", "outros"], {
      message: "Selecione o tipo",
    }),
    expenseDate: z.string().min(1, "Obrigatório"),
    description: z.string().min(1, "Obrigatório").max(280, "Máximo 280 caracteres"),
    projectId: z.string().optional(),
    costCenterId: z.string().optional(),
    kmTraveled: optionalNumber,
    tollAmount: optionalNumber,
    otherAmount: optionalNumber,
  })
  .superRefine((values, ctx) => {
    if (PROJECT_TYPES.includes(values.type) && !values.projectId) {
      ctx.addIssue({ code: "custom", path: ["projectId"], message: "Selecione o projeto" });
    }
    if (!PROJECT_TYPES.includes(values.type) && !values.costCenterId) {
      ctx.addIssue({ code: "custom", path: ["costCenterId"], message: "Selecione o centro de custo" });
    }
    if (KM_TYPES.includes(values.type) && !values.kmTraveled) {
      ctx.addIssue({ code: "custom", path: ["kmTraveled"], message: "Informe o km percorrido" });
    }
    if (values.type === "outros" && !values.otherAmount) {
      ctx.addIssue({ code: "custom", path: ["otherAmount"], message: "Informe o valor" });
    }
  });

type FormInput = z.input<typeof formSchema>;
type FormOutput = z.output<typeof formSchema>;

interface NewItemFormProps {
  reportId: string;
  costCenters: CostCenter[];
  rateRules: RateRule[];
  projects: ProjectOption[];
  onCreated: () => void;
}

export function NewItemForm({ reportId, costCenters, rateRules, projects, onCreated }: NewItemFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<FormInput, unknown, FormOutput>({ resolver: zodResolver(formSchema) });

  const type = watch("type");
  const kmTraveled = watch("kmTraveled");
  const tollAmount = watch("tollAmount");
  const otherAmount = watch("otherAmount");

  const rateKey = type ? rateKeyFor(type) : null;
  const rate = rateKey ? rateRules.find((r) => r.type === rateKey) : undefined;
  const isKmBased = type ? KM_TYPES.includes(type) : false;
  const isProjectType = type ? PROJECT_TYPES.includes(type) : false;

  useEffect(() => {
    if (type === "alimentacao" && rate) {
      setValue("otherAmount", rate.value);
    }
    if (type === "deslocamento_escritorio") {
      const suggested = costCenters.find((c) => c.name === "Deslocamento Escritório");
      if (suggested) setValue("costCenterId", suggested.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);

  const previewTotal = isKmBased
    ? Number(kmTraveled ?? 0) * (rate?.value ?? 0) + Number(tollAmount ?? 0)
    : Number(otherAmount ?? 0);

  async function onSubmit(values: FormOutput) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const kmBased = KM_TYPES.includes(values.type);
      const totalAmount = kmBased
        ? Number(values.kmTraveled ?? 0) * (rate?.value ?? 0) + Number(values.tollAmount ?? 0)
        : Number(values.otherAmount ?? 0);

      await createItem(reportId, {
        type: values.type,
        projectId: values.projectId,
        costCenterId: values.costCenterId,
        expenseDate: values.expenseDate,
        description: values.description,
        kmTraveled: kmBased ? values.kmTraveled : undefined,
        kmRate: kmBased ? rate?.value : undefined,
        tollAmount: kmBased ? (values.tollAmount ?? 0) : 0,
        otherAmount: kmBased ? 0 : Number(values.otherAmount ?? 0),
        requiresPreapproval: values.type === "alimentacao" || values.type === "outros",
        totalAmount,
      });
      onCreated();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível salvar o item. Tente novamente.",
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
          id="type"
          label="Tipo"
          variant="light"
          placeholder="Selecione..."
          options={TYPE_OPTIONS}
          error={errors.type?.message}
          {...register("type")}
        />
        <Input
          id="expenseDate"
          label="Data da despesa"
          type="date"
          variant="light"
          error={errors.expenseDate?.message}
          {...register("expenseDate")}
        />
      </div>

      {isProjectType && (
        <Select
          id="projectId"
          label="Projeto"
          variant="light"
          placeholder="Selecione..."
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
          error={errors.projectId?.message}
          {...register("projectId")}
        />
      )}

      {!isProjectType && type && (
        <Select
          id="costCenterId"
          label="Centro de custo"
          variant="light"
          placeholder="Selecione..."
          options={costCenters.map((c) => ({ value: c.id, label: c.name }))}
          error={errors.costCenterId?.message}
          {...register("costCenterId")}
        />
      )}

      {isKmBased && (
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="kmTraveled"
            label="Km percorrido"
            type="number"
            step="0.1"
            variant="light"
            error={errors.kmTraveled?.message}
            {...register("kmTraveled")}
          />
          <Input
            id="tollAmount"
            label="Pedágio (R$)"
            type="number"
            step="0.01"
            variant="light"
            error={errors.tollAmount?.message}
            {...register("tollAmount")}
          />
        </div>
      )}

      {type === "alimentacao" && (
        <Input
          id="otherAmount"
          label="Valor (R$)"
          type="number"
          step="0.01"
          variant="light"
          error={errors.otherAmount?.message}
          {...register("otherAmount")}
        />
      )}

      {type === "outros" && (
        <Input
          id="otherAmount"
          label="Valor (R$)"
          type="number"
          step="0.01"
          variant="light"
          error={errors.otherAmount?.message}
          {...register("otherAmount")}
        />
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="description" className="text-sm text-black/70">
          Descrição
        </label>
        <textarea
          id="description"
          rows={2}
          maxLength={280}
          className="rounded-md border border-black/20 bg-white px-3 py-2 text-black placeholder:text-black/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow"
          {...register("description")}
        />
        {errors.description && <p className="text-sm text-red-500">{errors.description.message}</p>}
      </div>

      {type && (
        <p className="text-sm text-black/70">
          Total do item: <span className="font-semibold text-black">{formatBRL(previewTotal)}</span>
          {(type === "alimentacao" || type === "outros") && " (requer pré-aprovação)"}
        </p>
      )}

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-fit">
        {submitting ? "Salvando..." : "Adicionar item"}
      </Button>
    </form>
  );
}
