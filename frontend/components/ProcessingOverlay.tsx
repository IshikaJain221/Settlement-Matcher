"use client";

const stages = [
  "Loading internal orders",
  "Loading bank settlements",
  "Running rule-based matcher",
  "Running AI-assisted matcher",
  "Compiling exception list",
];

export function ProcessingOverlay({ activeStage }: { activeStage: number }) {
  return (
    <div className="card p-6 mb-6 overflow-hidden relative">
      <div
        className="absolute top-0 left-0 h-[2px] w-1/3 scan-bar"
        style={{ background: "var(--accent)" }}
      />
      <div className="text-sm font-medium mb-4" style={{ color: "var(--text-primary)" }}>
        Running reconciliation pipeline…
      </div>
      <div className="flex flex-col gap-2.5">
        {stages.map((s, i) => {
          const done = i < activeStage;
          const active = i === activeStage;
          const dotClass = `w-1.5 h-1.5 rounded-full flex-shrink-0${active ? " pulse-dot" : ""}`;
          return (
            <div key={s} className="flex items-center gap-3 text-sm">
              <span
                className={dotClass}
                style={{
                  background: done ? "var(--success)" : active ? "var(--accent)" : "var(--border-strong)",
                }}
              />
              <span style={{ color: done || active ? "var(--text-primary)" : "var(--text-muted)" }}>
                {s}
              </span>
              {done && (
                <span className="text-xs ml-auto" style={{ color: "var(--success)" }}>
                  done
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
