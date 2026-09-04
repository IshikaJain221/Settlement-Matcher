export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    matched_rule: { bg: "var(--success-tint)", text: "var(--success)", label: "Matched · rules" },
    matched_ai: { bg: "var(--accent-tint)", text: "var(--accent)", label: "Matched · AI" },
    unresolved: { bg: "var(--danger-tint)", text: "var(--danger)", label: "Unresolved" },
  };
  const s = map[status] || map.unresolved;
  return (
    <span
      className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap"
      style={{ background: s.bg, color: s.text }}
    >
      {s.label}
    </span>
  );
}
