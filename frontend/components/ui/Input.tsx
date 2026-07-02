import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  variant?: "dark" | "light";
}

// variant="dark" é o usado pela tela de login (fundo pmon-black); "light" é pro
// resto do app, que ficou com tema claro (pmon-bg) a partir do painel de projetos.
const VARIANT_STYLES = {
  dark: {
    label: "text-white/80",
    input: "border-white/20 bg-neutral-900 text-white placeholder:text-white/40",
  },
  light: {
    label: "text-black/70",
    input: "border-black/20 bg-white text-black placeholder:text-black/40",
  },
};

export function Input({
  label,
  error,
  id,
  variant = "dark",
  className = "",
  ...props
}: InputProps) {
  const styles = VARIANT_STYLES[variant];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={`text-sm ${styles.label}`}>
        {label}
      </label>
      <input
        id={id}
        className={`rounded-md border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-pmon-yellow ${styles.input} ${className}`}
        {...props}
      />
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
