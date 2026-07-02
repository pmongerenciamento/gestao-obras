import type { ComponentType } from "react";
import {
  IconUpload,
  IconChartLine,
  IconLayoutBoard,
  IconTruck,
  IconColumns,
  IconFileAnalytics,
  type IconProps,
} from "@tabler/icons-react";

export interface ProjectModule {
  slug: string;
  label: string;
  description: string;
  icon: ComponentType<IconProps>;
}

// Lista compartilhada entre a nav da sidebar do projeto e o grid de módulos da Visão geral.
export const PROJECT_MODULES: ProjectModule[] = [
  {
    slug: "importacao",
    label: "Importar cronograma",
    description: "Envie o arquivo .mpp mais recente do projeto.",
    icon: IconUpload,
  },
  {
    slug: "linha-de-balanco",
    label: "Linha de balanço",
    description: "Progresso por pavimento ao longo do tempo.",
    icon: IconChartLine,
  },
  {
    slug: "gestao-a-vista",
    label: "Gestão à vista",
    description: "Quadros visuais de acompanhamento da obra.",
    icon: IconLayoutBoard,
  },
  {
    slug: "suprimentos",
    label: "Suprimentos",
    description: "Cronograma de compras e entregas.",
    icon: IconTruck,
  },
  {
    slug: "kanban",
    label: "Kanban",
    description: "Atividades organizadas em cards.",
    icon: IconColumns,
  },
  {
    slug: "relatorios",
    label: "Relatórios",
    description: "Exportação de painéis em PDF e Excel.",
    icon: IconFileAnalytics,
  },
];
