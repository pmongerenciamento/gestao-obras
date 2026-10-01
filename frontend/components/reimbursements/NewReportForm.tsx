"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { createReport } from "@/lib/api/reimbursement-mutations";
import { getCurrentMonthRange } from "@/lib/date/month-range";

const formSchema = z
  .object({
    periodStart: z.string().min(1, "Obrigatório"),
    periodEnd: z.string().min(1, "Obrigatório"),
  })
  .refine((values) => values.periodEnd >= values.periodStart, {
    message: "Deve ser igual ou depois do início",
    path: ["periodEnd"],
  });

type FormValues = z.infer<typeof formSchema>;

interface NewReportFormProps {
  onCreated: (reportId: string) => void;
}

export function NewReportForm({ onCreated }: NewReportFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const defaults = getCurrentMonthRange();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { periodStart: defaults.start, periodEnd: defaults.end },
  });

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const reportId = await createReport({ periodStart: values.periodStart, periodEnd: values.periodEnd });
      onCreated(reportId);
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Não foi possível criar o relatório. Tente novamente.",
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
          id="periodStart"
          label="Início do período"
          type="date"
          variant="light"
          error={errors.periodStart?.message}
          {...register("periodStart")}
        />
        <Input
          id="periodEnd"
          label="Fim do período"
          type="date"
          variant="light"
          error={errors.periodEnd?.message}
          {...register("periodEnd")}
        />
      </div>

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-fit">
        {submitting ? "Criando..." : "Criar relatório"}
      </Button>
    </form>
  );
}
