import type { SelectHTMLAttributes } from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: readonly SelectOption[];
  placeholder?: string;
  error?: string;
  variant?: "dark" | "light";
}

// Mesmo padrão visual (e mesma dualidade de tema) do components/ui/Input.tsx.
const VARIANT_STYLES = {
  dark: {
    label: "text-white/80",
    select: "border-white/20 bg-neutral-900 text-white",
  },
  light: {
    label: "text-black/70",
    select: "border-black/20 bg-white text-black",
  },
};

export function Select({
  label,
  options,
  placeholder,
  error,
  id,
  variant = "light",
  className = "",
  ...props
}: SelectProps) {
  const styles = VARIANT_STYLES[variant];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={`text-sm ${styles.label}`}>
        {label}
      </label>
      <select
        id={id}
        className={`rounded-md border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-pmon-yellow ${styles.select} ${className}`}
        {...props}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
