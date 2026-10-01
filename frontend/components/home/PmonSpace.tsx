import Image from "next/image";

// TODO: substituir por carrossel real quando houver conteúdo dinâmico pra rotacionar
export function PmonSpace() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-black/10 bg-white p-8 text-center">
      <Image src="/logo/LOGO_PMON.png" alt="PMON" width={64} height={64} className="h-16 w-auto" />
      <div>
        <p className="text-sm font-medium text-black">Espaço PMON</p>
        <p className="text-xs text-black/50">Novidades e comunicados da equipe em breve por aqui.</p>
      </div>
    </div>
  );
}
