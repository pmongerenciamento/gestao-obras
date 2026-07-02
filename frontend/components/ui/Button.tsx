import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
}

export function Button({ isLoading, disabled, children, className = "", ...props }: ButtonProps) {
  return (
    <button
      disabled={disabled || isLoading}
      className={`w-full rounded-md bg-pmon-yellow px-4 py-2 font-semibold text-pmon-black transition-colors hover:bg-pmon-yellow/90 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
