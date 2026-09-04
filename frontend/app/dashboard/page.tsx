"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  runMatch, getStats, getRecords, askQuestion, getScenarios, getSuggestions,
  Stats, Record_, UnknownSettlement, Scenario,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ProcessingOverlay } from "@/components/ProcessingOverlay";

type Tab = "all" | "exceptions";
type ChatMsg = { role: "user" | "assistant"; text: string };

export default function Dashboard() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("original");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [hasRun, setHasRun] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [records, setRecords] = useState<Record_[]>([]);
  const [unknowns, setUnknowns] = useState<UnknownSettlement[]>([]);
  const [tab, setTab] = useState<Tab>("all");
  const [error, setError] = useState<string | null>(null);

  const [chatInput, setChatInput] = useState("");
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chips, setChips] = useState<string[]>([]);

  useEffect(() => {
    getScenarios().then((r) => setScenarios(r.scenarios)).catch(() => {});
  }, []);

  const handleRun = useCallback(async (scenarioKey?: string) => {
    const target = scenarioKey || scenario;
    setLoading(true);
    setError(null);
    setStage(0);
    setChatMsgs([]);
    try {
      const stageTimer = setInterval(() => {
        setStage((s) => Math.min(s + 1, 4));
      }, 450);

      await runMatch(target);
      const [s, r, sugg] = await Promise.all([getStats(target), getRecords(target), getSuggestions(target)]);

      clearInterval(stageTimer);
      setStage(5);
      await new Promise((res) => setTimeout(res, 300));

      setStats(s);
      setRecords(r.records);
      setUnknowns(r.unknown_settlements);
      setChips(sugg.suggestions);
      setHasRun(true);
    } catch {
      setError(
        "Couldn't reach the backend at http://localhost:8000 — make sure the FastAPI server is running."
      );
    } finally {
      setLoading(false);
    }
  }, [scenario]);

  function handleScenarioChange(key: string) {
    setScenario(key);
    setHasRun(false);
    setStats(null);
  }

  async function sendQuestion(q: string) {
    if (!q.trim()) return;
    setChatMsgs((m) => [...m, { role: "user", text: q }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await askQuestion(q, scenario);
      setChatMsgs((m) => [...m, { role: "assistant", text: res.answer }]);
    } catch {
      setChatMsgs((m) => [...m, { role: "assistant", text: "Something went wrong answering that — try again." }]);
    } finally {
      setChatLoading(false);
    }
  }

  async function handleAsk() {
    await sendQuestion(chatInput.trim());
  }

  const exceptionRecords = records.filter((r) => r.status !== "matched_rule");
  const currentScenarioMeta = scenarios.find((s) => s.key === scenario);

  return (
    <div style={{ minHeight: "100vh" }}>
      <nav className="border-b sticky top-0 z-10" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 flex-shrink-0">
            <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-semibold" style={{ background: "var(--accent)" }}>
              SM
            </div>
            <span className="font-semibold text-[15px]" style={{ color: "var(--text-primary)" }}>
              Settlement Matcher
            </span>
          </Link>

          <div className="flex items-center gap-3">
            <select
              value={scenario}
              onChange={(e) => handleScenarioChange(e.target.value)}
              className="text-sm px-3 py-2 rounded-lg outline-none"
              style={{ border: "1px solid var(--border-strong)", color: "var(--text-primary)", background: "var(--surface)" }}
            >
              {scenarios.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
            <button onClick={() => handleRun()} disabled={loading} className="btn-primary text-sm px-4 py-2 whitespace-nowrap">
              {loading ? "Running…" : hasRun ? "Re-run" : "Run reconciliation"}
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {currentScenarioMeta && (
          <div className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
            <span className="font-medium" style={{ color: "var(--text-primary)" }}>{currentScenarioMeta.label}</span>
            {" — "}{currentScenarioMeta.description}
          </div>
        )}

        {error && (
          <div className="card p-4 mb-6 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            {error}
          </div>
        )}

        {loading && <ProcessingOverlay activeStage={stage} />}

        {!hasRun && !loading && (
          <div className="card p-12 text-center mb-6">
            <div className="font-medium text-lg mb-2" style={{ color: "var(--text-primary)" }}>
              No results yet
            </div>
            <div className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
              Pick a dataset above and run the pipeline to see match rate, exceptions, and the Q&amp;A chat.
            </div>
            <button onClick={() => handleRun()} className="btn-primary text-sm px-5 py-2.5">
              Run reconciliation →
            </button>
          </div>
        )}

        {hasRun && stats && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8 fade-up">
              <StatCard label="Match rate" value={`${stats.match_rate_pct}%`} accent />
              <StatCard label="Total records" value={stats.total_orders.toString()} />
              <StatCard label="Matched · rules" value={stats.matched_rule.toString()} tint="var(--success-tint)" color="var(--success)" />
              <StatCard label="Matched · AI" value={stats.matched_ai.toString()} tint="var(--accent-tint)" color="var(--accent)" />
              <StatCard label="Unresolved" value={stats.unresolved.toString()} tint="var(--danger-tint)" color="var(--danger)" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <div className="flex items-center gap-1 mb-4">
                  <TabButton active={tab === "all"} onClick={() => setTab("all")}>
                    All records ({records.length})
                  </TabButton>
                  <TabButton active={tab === "exceptions"} onClick={() => setTab("exceptions")}>
                    Exceptions ({exceptionRecords.length + unknowns.length})
                  </TabButton>
                </div>

                <div className="card overflow-hidden">
                  {tab === "all" && (
                    <div className="overflow-x-auto" style={{ maxHeight: "560px", overflowY: "auto" }}>
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left" style={{ borderColor: "var(--border)" }}>
                            <Th>Order</Th>
                            <Th>Customer</Th>
                            <Th>Amount</Th>
                            {scenario === "combined" && <Th>Scenario</Th>}
                            <Th>Status</Th>
                            <Th>Reason</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {records.map((r) => (
                            <tr key={`${r.scenario || ""}-${r.order_id}`} className="border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                              <Td className="mono">{r.order_id}</Td>
                              <Td>{r.customer}</Td>
                              <Td className="mono">₹{r.order_amount.toLocaleString("en-IN")}</Td>
                              {scenario === "combined" && (
                                <Td muted className="text-xs">{r.scenario}</Td>
                              )}
                              <Td><StatusBadge status={r.status} /></Td>
                              <Td className="max-w-xs" muted>{r.reason}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {tab === "exceptions" && (
                    <div className="divide-y" style={{ borderColor: "var(--border)", maxHeight: "560px", overflowY: "auto" }}>
                      {exceptionRecords.length === 0 && unknowns.length === 0 && (
                        <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
                          No exceptions — everything matched cleanly.
                        </div>
                      )}
                      {exceptionRecords.map((r) => (
                        <div key={`${r.scenario || ""}-${r.order_id}`} className="p-4">
                          <div className="flex items-center justify-between mb-1.5 gap-2">
                            <span className="font-medium text-sm mono" style={{ color: "var(--text-primary)" }}>
                              {r.order_id} {scenario === "combined" && <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>· {r.scenario}</span>}
                            </span>
                            <StatusBadge status={r.status} />
                          </div>
                          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                            {r.reason}
                          </div>
                          {r.resolved_by === "ai_assisted" && (
                            <div className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
                              Confidence: {(r.confidence * 100).toFixed(0)}% · resolved by AI-assisted matcher
                            </div>
                          )}
                        </div>
                      ))}
                      {unknowns.map((u) => (
                        <div key={u.utr} className="p-4" style={{ background: "var(--danger-tint)" }}>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-medium text-sm mono" style={{ color: "var(--text-primary)" }}>{u.utr}</span>
                            <span className="text-xs font-medium px-2.5 py-1 rounded-full" style={{ background: "var(--surface)", color: "var(--danger)" }}>
                              Unknown settlement
                            </span>
                          </div>
                          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>{u.reason}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="lg:col-span-1">
                <div className="font-medium text-sm mb-4" style={{ color: "var(--text-primary)" }}>
                  Ask about a record
                </div>
                <div className="card flex flex-col" style={{ height: "560px" }}>
                  <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
                    {chatMsgs.length === 0 && (
                      <div className="flex flex-col gap-2">
                        <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>
                          Try asking:
                        </div>
                        {chips.map((c) => (
                          <button
                            key={c}
                            onClick={() => sendQuestion(c)}
                            className="text-left text-sm px-3 py-2 rounded-lg"
                            style={{ background: "var(--accent-tint)", color: "var(--accent)", border: "1px solid transparent" }}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                    )}
                    {chatMsgs.map((m, i) => (
                      <div
                        key={i}
                        className="text-sm px-3 py-2 rounded-lg whitespace-pre-line"
                        style={{
                          background: m.role === "user" ? "var(--accent-tint)" : "var(--bg)",
                          color: "var(--text-primary)",
                          alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                          maxWidth: "90%",
                        }}
                      >
                        {m.text}
                      </div>
                    ))}
                    {chatLoading && (
                      <div className="text-sm" style={{ color: "var(--text-muted)" }}>Thinking…</div>
                    )}
                  </div>
                  <div className="border-t p-3 flex gap-2" style={{ borderColor: "var(--border)" }}>
                    <input
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAsk()}
                      placeholder="Ask about an order or exception…"
                      className="flex-1 text-sm px-3 py-2 rounded-lg outline-none"
                      style={{ border: "1px solid var(--border-strong)" }}
                    />
                    <button onClick={handleAsk} disabled={chatLoading} className="btn-primary text-sm px-4 py-2">
                      Ask
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, accent, tint, color }: { label: string; value: string; accent?: boolean; tint?: string; color?: string }) {
  return (
    <div className="card p-4" style={accent ? { background: "var(--accent)", borderColor: "var(--accent)" } : tint ? { background: tint } : {}}>
      <div className="text-xs font-medium mb-1.5" style={{ color: accent ? "rgba(255,255,255,0.8)" : "var(--text-secondary)" }}>{label}</div>
      <div className="text-2xl font-semibold" style={{ color: accent ? "white" : color || "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="text-sm font-medium px-3.5 py-2 rounded-lg"
      style={{
        background: active ? "var(--surface)" : "transparent",
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        border: active ? "1px solid var(--border)" : "1px solid transparent",
      }}
    >
      {children}
    </button>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-4 py-3 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>{children}</th>;
}

function Td({ children, className, muted }: { children: React.ReactNode; className?: string; muted?: boolean }) {
  return (
    <td className={`px-4 py-3 ${className || ""}`} style={{ color: muted ? "var(--text-secondary)" : "var(--text-primary)" }}>
      {children}
    </td>
  );
}
