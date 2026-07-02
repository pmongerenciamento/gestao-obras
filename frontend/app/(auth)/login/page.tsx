import Image from "next/image";
import { LoginForm } from "@/components/auth/LoginForm";

// Tela de login: logo PMON, campos de e-mail/senha, botão LOGIN, link "Esqueceu a senha?"
// Sem cadastro público — autenticação via Supabase Auth

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-pmon-black px-4">
      <div className="w-full max-w-[400px] rounded-lg border border-white/10 bg-neutral-950 p-8">
        <Image
          src="/logo/LOGO_PMON.png"
          alt="PMON"
          width={64}
          height={64}
          priority
          className="mx-auto mb-8 h-16 w-auto"
        />
        <LoginForm />
      </div>
    </div>
  );
}
