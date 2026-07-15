export function EmptyState({
  title,
  description,
}: Readonly<{ title: string; description?: string }>) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      {description && <p>{description}</p>}
    </div>
  );
}

export function ErrorState({ error }: Readonly<{ error: unknown }>) {
  const message = error instanceof Error ? error.message : String(error);
  return <div className="error-state">{message}</div>;
}

export function Badge({ children, tone = "neutral" }: Readonly<{ children: React.ReactNode; tone?: "neutral" | "accent" | "green" | "gold" }>) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
