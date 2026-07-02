"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { BRAZILIAN_STATES } from "@/lib/brazilian-states";
import {
  TIPOLOGIA_OBRA_OPTIONS,
  TIPOLOGIA_CONSTRUTIVA_OPTIONS,
  VERTICAL_TIPOLOGIAS,
  type TipologiaObra,
  type TipologiaConstrutiva,
} from "@/types/project";
import { createProject, uploadProjectImage } from "@/lib/api/create-project";

const tipologiaObraValues = TIPOLOGIA_OBRA_OPTIONS.map((o) => o.value) as [
  TipologiaObra,
  ...TipologiaObra[],
];
const tipologiaConstrutivaValues = TIPOLOGIA_CONSTRUTIVA_OPTIONS.map((o) => o.value) as [
  TipologiaConstrutiva,
  ...TipologiaConstrutiva[],
];

const emptyToUndefined = (val: unknown) => (val === "" ? undefined : val);
const optionalInt = z.preprocess(emptyToUndefined, z.coerce.number().int().positive().optional());
const optionalNumber = z.preprocess(emptyToUndefined, z.coerce.number().positive().optional());
const optionalString = z.preprocess(emptyToUndefined, z.string().optional());

const formSchema = z
  .object({
    name: z.string().min(1, "Obrigatório"),
    clientName: z.string().min(1, "Obrigatório"),
    city: z.string().min(1, "Obrigatório"),
    state: z.string().length(2, "Selecione o estado"),
    tipologiaObra: z.enum(tipologiaObraValues, { message: "Selecione a tipologia" }),
    tipologiaConstrutiva: z.enum(tipologiaConstrutivaValues, {
      message: "Selecione a tipologia construtiva",
    }),
    tipologiaConstrutivaOutros: optionalString,
    numTorres: optionalInt,
    numPavimentos: optionalInt,
    numUnidades: optionalInt,
    numLotes: optionalInt,
    areaConstruida: optionalNumber,
    areaPrivativa: optionalNumber,
    orcamento: optionalNumber,
    dataBaseOrcamento: optionalString,
    prazoEstimadoMeses: optionalInt,
  })
  .superRefine((data, ctx) => {
    if (data.tipologiaConstrutiva === "outros" && !data.tipologiaConstrutivaOutros?.trim()) {
      ctx.addIssue({
        code: "custom",
        path: ["tipologiaConstrutivaOutros"],
        message: "Descreva a tipologia construtiva",
      });
    }

    if (VERTICAL_TIPOLOGIAS.includes(data.tipologiaObra)) {
      (["numTorres", "numPavimentos", "numUnidades"] as const).forEach((field) => {
        if (!data[field]) {
          ctx.addIssue({ code: "custom", path: [field], message: "Obrigatório" });
        }
      });
    }

    if (data.tipologiaObra === "loteamento" && !data.numLotes) {
      ctx.addIssue({ code: "custom", path: ["numLotes"], message: "Obrigatório" });
    }
  });

// z.coerce/preprocess faz o schema de entrada (o que os inputs não controlados
// mandam, ex.: string de <input type="number">) divergir do de saída (já
// coagido pro tipo final) — os dois generics do useForm evitam esse atrito
// de tipos com o zodResolver.
type FormInput = z.input<typeof formSchema>;
type FormOutput = z.output<typeof formSchema>;

export function NewProjectForm() {
  const router = useRouter();
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormInput, unknown, FormOutput>({ resolver: zodResolver(formSchema) });

  const tipologiaObra = watch("tipologiaObra");
  const tipologiaConstrutiva = watch("tipologiaConstrutiva");
  const isVertical = tipologiaObra && VERTICAL_TIPOLOGIAS.includes(tipologiaObra);
  const isLoteamento = tipologiaObra === "loteamento";

  function handleImageChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setImageFile(file);
    setImagePreview(file ? URL.createObjectURL(file) : null);
  }

  async function onSubmit(values: FormOutput) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const imageUrl = imageFile ? await uploadProjectImage(imageFile) : null;

      const id = await createProject({
        name: values.name,
        clientName: values.clientName,
        city: values.city,
        state: values.state,
        tipologiaObra: values.tipologiaObra,
        tipologiaConstrutiva: values.tipologiaConstrutiva,
        tipologiaConstrutivaOutros: values.tipologiaConstrutivaOutros,
        numTorres: values.numTorres,
        numPavimentos: values.numPavimentos,
        numUnidades: values.numUnidades,
        numLotes: values.numLotes,
        areaConstruida: values.areaConstruida,
        areaPrivativa: values.areaPrivativa,
        orcamento: values.orcamento,
        dataBaseOrcamento: values.dataBaseOrcamento,
        prazoEstimadoMeses: values.prazoEstimadoMeses,
        imageUrl,
      });

      router.push(`/projetos/${id}`);
      router.refresh();
    } catch {
      setSubmitError("Não foi possível salvar o projeto. Tente novamente.");
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-8"
    >
      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-black/70">Identificação</h2>
        <Input
          id="name"
          label="Nome do projeto"
          variant="light"
          error={errors.name?.message}
          {...register("name")}
        />
        <Input
          id="clientName"
          label="Cliente"
          variant="light"
          error={errors.clientName?.message}
          {...register("clientName")}
        />
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="city"
            label="Cidade"
            variant="light"
            error={errors.city?.message}
            {...register("city")}
          />
          <Select
            id="state"
            label="Estado"
            placeholder="Selecione"
            options={BRAZILIAN_STATES}
            error={errors.state?.message}
            {...register("state")}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-black/70">Tipologia</h2>
        <Select
          id="tipologiaObra"
          label="Tipologia da obra"
          placeholder="Selecione"
          options={TIPOLOGIA_OBRA_OPTIONS}
          error={errors.tipologiaObra?.message}
          {...register("tipologiaObra")}
        />
        <Select
          id="tipologiaConstrutiva"
          label="Tipologia construtiva"
          placeholder="Selecione"
          options={TIPOLOGIA_CONSTRUTIVA_OPTIONS}
          error={errors.tipologiaConstrutiva?.message}
          {...register("tipologiaConstrutiva")}
        />
        {tipologiaConstrutiva === "outros" && (
          <Input
            id="tipologiaConstrutivaOutros"
            label="Descreva a tipologia construtiva"
            variant="light"
            error={errors.tipologiaConstrutivaOutros?.message}
            {...register("tipologiaConstrutivaOutros")}
          />
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-black/70">Métricas</h2>
        {isVertical && (
          <div className="grid grid-cols-3 gap-4">
            <Input
              id="numTorres"
              label="Torres"
              type="number"
              variant="light"
              error={errors.numTorres?.message}
              {...register("numTorres")}
            />
            <Input
              id="numPavimentos"
              label="Pavimentos"
              type="number"
              variant="light"
              error={errors.numPavimentos?.message}
              {...register("numPavimentos")}
            />
            <Input
              id="numUnidades"
              label="Unidades"
              type="number"
              variant="light"
              error={errors.numUnidades?.message}
              {...register("numUnidades")}
            />
          </div>
        )}
        {isLoteamento && (
          <Input
            id="numLotes"
            label="Número de lotes"
            type="number"
            variant="light"
            error={errors.numLotes?.message}
            {...register("numLotes")}
          />
        )}
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="areaConstruida"
            label="Área construída (m²)"
            type="number"
            step="0.01"
            variant="light"
            error={errors.areaConstruida?.message}
            {...register("areaConstruida")}
          />
          <Input
            id="areaPrivativa"
            label="Área privativa (m²)"
            type="number"
            step="0.01"
            variant="light"
            error={errors.areaPrivativa?.message}
            {...register("areaPrivativa")}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-black/70">Orçamento e prazo</h2>
        <Input
          id="orcamento"
          label="Orçamento (R$)"
          type="number"
          step="0.01"
          variant="light"
          error={errors.orcamento?.message}
          {...register("orcamento")}
        />
        <div className="grid grid-cols-2 gap-4">
          <Input
            id="dataBaseOrcamento"
            label="Data-base do orçamento"
            type="date"
            variant="light"
            error={errors.dataBaseOrcamento?.message}
            {...register("dataBaseOrcamento")}
          />
          <Input
            id="prazoEstimadoMeses"
            label="Prazo estimado (meses)"
            type="number"
            variant="light"
            error={errors.prazoEstimadoMeses?.message}
            {...register("prazoEstimadoMeses")}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-black/70">Perspectiva 3D</h2>
        <input type="file" accept="image/*" onChange={handleImageChange} className="text-sm" />
        {imagePreview && (
          // eslint-disable-next-line @next/next/no-img-element -- preview local via object URL, não passa pelo otimizador do next/image
          <img
            src={imagePreview}
            alt="Pré-visualização"
            className="h-[160px] w-full rounded-md object-cover"
          />
        )}
      </section>

      {submitError && <p className="text-sm text-red-500">{submitError}</p>}

      <Button type="submit" isLoading={submitting} className="w-full">
        {submitting ? "Salvando..." : "Salvar projeto"}
      </Button>
    </form>
  );
}
