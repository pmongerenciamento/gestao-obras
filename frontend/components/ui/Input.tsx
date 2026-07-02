import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function Input({ label, error, id, className = "", ...props }: InputProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm text-white/80">
        {label}
      </label>
      <input
        id={id}
        className={`rounded-md border border-white/20 bg-neutral-900 px-3 py-2 text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-pmon-yellow ${className}`}
        {...props}
      />
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
