"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Client } from "@/types/client";
import { Button } from "@/components/ui/Button";
import { NewClientForm } from "@/components/clients/NewClientForm";

interface ClientsViewProps {
  clients: Client[];
}

export function ClientsView({ clients }: ClientsViewProps) {
  const router = useRouter();
  const [formOpen, setFormOpen] = useState(false);

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-black">Clientes</h1>
        <Button onClick={() => setFormOpen((open) => !open)}>
          {formOpen ? "Cancelar" : "Novo cliente"}
        </Button>
      </div>

      {formOpen && (
        <NewClientForm
          onCreated={() => {
            setFormOpen(false);
            router.refresh();
          }}
        />
      )}

      <div className="rounded-lg border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="rounded-t-lg border-b border-black/10 bg-black/[0.02] text-xs uppercase text-black/50">
            <tr>
              <th className="rounded-tl-lg px-4 py-3 font-medium">Código</th>
              <th className="px-4 py-3 font-medium">Nome</th>
              <th className="px-4 py-3 font-medium">Contato</th>
              <th className="rounded-tr-lg px-4 py-3 font-medium">E-mail</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => (
              <tr key={client.id} className="border-b border-black/5 last:border-0">
                <td className="px-4 py-3 font-mono text-black/70">{client.code}</td>
                <td className="px-4 py-3 text-black">{client.legalName}</td>
                <td className="px-4 py-3 text-black/70">{client.contactName ?? "—"}</td>
                <td className="px-4 py-3 text-black/70">{client.contactEmail ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {clients.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-black/50">Nenhum cliente cadastrado ainda.</p>
        )}
      </div>
    </>
  );
}
