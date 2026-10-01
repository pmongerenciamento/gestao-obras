// TODO: substituir por mural_posts quando o schema for criado
const UPDATES = [
  {
    id: "1",
    dotColor: "bg-pmon-yellow",
    text: "Módulo de Clientes disponível no CRM.",
    relativeDate: "Hoje, 08:30",
  },
  {
    id: "2",
    dotColor: "bg-green-500",
    text: "Cronograma do projeto atualizado com sucesso.",
    relativeDate: "Ontem, 17:12",
  },
  {
    id: "3",
    dotColor: "bg-blue-500",
    text: "Correção de datas na Linha de Balanço.",
    relativeDate: "2 dias atrás",
  },
  {
    id: "4",
    dotColor: "bg-red-500",
    text: "Manutenção programada concluída sem impacto no sistema.",
    relativeDate: "3 dias atrás",
  },
];

export function UpdatesFeed() {
  return (
    <div className="rounded-lg border border-black/10 bg-white p-4">
      <h2 className="mb-4 text-sm font-semibold text-black/70">Mural de atualizações</h2>
      <ul className="flex flex-col gap-3">
        {UPDATES.map((update) => (
          <li key={update.id} className="flex items-start gap-3">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${update.dotColor}`} />
            <div>
              <p className="text-sm text-black">{update.text}</p>
              <p className="text-xs text-black/40">{update.relativeDate}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
