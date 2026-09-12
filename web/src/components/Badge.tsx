export type BadgeTone = "ink" | "accent" | "muted" | "outline";

export default function Badge({
  children,
  tone = "outline",
  className = "",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  const cls =
    tone === "accent"
      ? "bg-accent text-paper border-accent"
      : tone === "ink"
        ? "bg-ink text-paper border-ink"
        : tone === "muted"
          ? "bg-synth text-paper border-synth"
          : "border-ink text-ink";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs uppercase tracking-wider ${cls} ${className}`}
    >
      {children}
    </span>
  );
}
