import type { ComponentType } from "react";
import {
  IconBuildingSkyscraper,
  IconUsersGroup,
  IconCoin,
  IconReceipt2,
  type IconProps,
} from "@tabler/icons-react";
import type { ModuleCode } from "@/lib/api/modules";

export interface HomeModule {
  code: ModuleCode;
  label: string;
  description: string;
  icon: ComponentType<IconProps>;
  href: string | null; // null = módulo sem tela própria ainda ("Em breve")
}

// Lista fixa dos 4 módulos do sistema (backend/migrations/023_create_permission_catalog.sql).
// O grid da tela inicial filtra isto pelos módulos que o usuário logado tem em profile_modules
// — exceto 'reembolso', que é aberto a qualquer autenticado (ver ModuleGrid.tsx).
export const HOME_MODULES: HomeModule[] = [
  {
    code: "engenharia",
    label: "Engenharia",
    description: "Projetos, cronogramas e acompanhamento de obra.",
    icon: IconBuildingSkyscraper,
    href: "/projetos",
  },
  {
    code: "crm",
    label: "CRM / Vendas",
    description: "Clientes, propostas e contratos.",
    icon: IconUsersGroup,
    href: "/crm",
  },
  {
    code: "financeiro",
    label: "Financeiro",
    description: "Faturamento e controle financeiro das obras.",
    icon: IconCoin,
    href: null,
  },
  {
    code: "reembolso",
    label: "Reembolso",
    description: "Solicitações e aprovações de reembolso.",
    icon: IconReceipt2,
    href: "/reembolso",
  },
];
