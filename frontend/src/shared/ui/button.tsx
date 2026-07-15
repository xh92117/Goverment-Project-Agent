import { Loader2Icon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  className = "",
  variant = "secondary",
  loading = false,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
}) {
  return (
    <button
      className={`ui-button ui-button-${variant} ${className}`}
      disabled={Boolean(disabled) || loading}
      {...props}
    >
      {loading && <Loader2Icon className="spin" size={15} />}
      {children}
    </button>
  );
}
