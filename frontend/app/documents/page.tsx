"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
} from "recharts";
import { uploadDocument, chatWithDocument, getDocAnalysis, DocAnalysis, Transaction } from "@/lib/api";

type ChatMsg = { role: "user" | "assistant"; text: string; method?: string };

const COLORS = ["#3B5BFB", "#12B76A", "#F79009", "#F04438", "#7C3AED", "#0EA5E9", "#EC4899", "#84CC16"];

export default function DocumentsPage() {
  const [uploading, setUploading] = useState(false);
  const [docId, setDocId] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const [embeddingMethod, setEmbeddingMethod] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<DocAnalysis | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [extractionMethod, setExtractionMethod] = useState("");
  const [analyzing, setAnalyzing] = useState(false);

  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const res = await uploadDocument(file);
      setDocId(res.doc_id);
      setFilename(res.filename);
      setEmbeddingMethod(res.embedding_method);
      setChatMsgs([]);
      setAnalysis(null);

      setAnalyzing(true);
      const a = await getDocAnalysis(res.doc_id);
      setAnalysis(a.analysis);
      setTransactions(a.transactions);
      setExtractionMethod(a.extraction_method);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong uploading that file.");
    } finally {
      setUploading(false);
      setAnalyzing(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
  }

  async function sendQuestion(q: string) {
    if (!q.trim() || !docId) return;
    setChatMsgs((m) => [...m, { role: "user", text: q }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await chatWithDocument(docId, q);
      setChatMsgs((m) => [...m, { role: "assistant", text: res.answer, method: res.retrieval_method }]);
    } catch {
      setChatMsgs((m) => [...m, { role: "assistant", text: "Something went wrong answering that." }]);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh" }}>
      <nav className="border-b sticky top-0 z-10" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-semibold" style={{ background: "var(--accent)" }}>SM</div>
            <span className="font-semibold text-[15px]" style={{ color: "var(--text-primary)" }}>Settlement Matcher</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-sm" style={{ color: "var(--text-secondary)" }}>Reconciliation</Link>
            <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>Document Analysis</span>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold mb-1" style={{ color: "var(--text-primary)" }}>Financial Document Analysis</h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Upload a bank statement (PDF, CSV, or text) — get a spending breakdown and ask questions about it.
          </p>
        </div>

        {error && (
          <div className="card p-4 mb-6 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>{error}</div>
        )}

        {!docId && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className="card p-16 text-center cursor-pointer"
            style={{ borderStyle: "dashed", borderWidth: 2, borderColor: dragActive ? "var(--accent)" : "var(--border-strong)",
                     background: dragActive ? "var(--accent-tint)" : "var(--surface)" }}
          >
            <input ref={fileInputRef} type="file" accept=".pdf,.csv,.txt" className="hidden"
                   onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
            {uploading ? (
              <div className="text-sm font-medium" style={{ color: "var(--accent)" }}>Processing document…</div>
            ) : (
              <>
                <div className="font-medium text-lg mb-2" style={{ color: "var(--text-primary)" }}>
                  Drop a bank statement here, or click to browse
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>Supports PDF, CSV, and TXT</div>
              </>
            )}
          </div>
        )}

        {docId && (
          <>
            <div className="flex items-center justify-between mb-6">
              <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                <span className="font-medium" style={{ color: "var(--text-primary)" }}>{filename}</span>
                {" — "}embeddings: {embeddingMethod === "gemini_embeddings" ? "Gemini" : "keyword fallback"}
              </div>
              <button onClick={() => { setDocId(null); setAnalysis(null); }} className="btn-secondary text-sm px-3 py-1.5">
                Upload a different file
              </button>
            </div>

            {analyzing && (
              <div className="card p-8 text-center mb-6 text-sm" style={{ color: "var(--text-secondary)" }}>
                Extracting transactions…
              </div>
            )}

            {analysis && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <StatCard label="Transactions" value={analysis.total_transactions.toString()} />
                  <StatCard label="Money in" value={`₹${analysis.total_in.toLocaleString("en-IN")}`} color="var(--success)" tint="var(--success-tint)" />
                  <StatCard label="Money out" value={`₹${analysis.total_out.toLocaleString("en-IN")}`} color="var(--danger)" tint="var(--danger-tint)" />
                  <StatCard label="Net" value={`₹${analysis.net.toLocaleString("en-IN")}`} accent />
                </div>

                <div className="text-xs mb-6" style={{ color: "var(--text-muted)" }}>
                  Extraction method: {extractionMethod === "gemini_llm" ? "Gemini (LLM-categorized)" : "regex + keyword fallback — set GEMINI_API_KEY for smarter, LLM-based categorization"}
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                  <div className="lg:col-span-1 card p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>Spending by category</div>
                      <div className="text-xs font-medium" style={{ color: analysis.net >= 0 ? "var(--success)" : "var(--danger)" }}>
                        {analysis.net >= 0 ? "Profit" : "Loss"}: ₹{Math.abs(analysis.net).toLocaleString("en-IN")}
                      </div>
                    </div>
                    {analysis.category_breakdown.length > 0 ? (
                      <>
                        <ResponsiveContainer width="100%" height={200}>
                          <PieChart>
                            <Pie data={analysis.category_breakdown} dataKey="amount" nameKey="category" cx="50%" cy="50%" outerRadius={75}>
                              {analysis.category_breakdown.map((_, i) => (
                                <Cell key={i} fill={COLORS[i % COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v: any) => `₹${Number(v ?? 0).toLocaleString("en-IN")}`} />
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="flex flex-col gap-1.5 mt-2">
                          {analysis.category_breakdown.map((c, i) => {
                            const pct = analysis.total_out ? ((c.amount / analysis.total_out) * 100).toFixed(1) : "0.0";
                            return (
                              <div key={c.category} className="flex items-center justify-between text-xs">
                                <span className="flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
                                  <span className="w-2 h-2 rounded-full inline-block" style={{ background: COLORS[i % COLORS.length] }} />
                                  {c.category}
                                </span>
                                <span style={{ color: "var(--text-primary)" }}>₹{c.amount.toLocaleString("en-IN")} ({pct}%)</span>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : (
                      <div className="text-sm text-center py-16" style={{ color: "var(--text-muted)" }}>No category data</div>
                    )}
                  </div>

                  <div className="lg:col-span-2 card p-5">
                    <div className="font-medium text-sm mb-4" style={{ color: "var(--text-primary)" }}>Monthly net flow</div>
                    {analysis.monthly_trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={analysis.monthly_trend}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                          <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(v: any) => `₹${Number(v ?? 0).toLocaleString("en-IN")}`} />
                          <Legend />
                          <Bar dataKey="net" name="Net" radius={[4, 4, 0, 0]}>
                            {analysis.monthly_trend.map((m, i) => (
                              <Cell key={i} fill={m.net >= 0 ? "var(--success)" : "var(--danger)"} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="text-sm text-center py-16" style={{ color: "var(--text-muted)" }}>No monthly data — dates weren&apos;t recognized</div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="lg:col-span-2 card overflow-hidden">
                    <div className="font-medium text-sm p-4 border-b" style={{ color: "var(--text-primary)", borderColor: "var(--border)" }}>
                      Top transactions
                    </div>
                    <div style={{ maxHeight: 360, overflowY: "auto" }}>
                      <table className="w-full text-sm">
                        <tbody>
                          {analysis.top_transactions.map((t, i) => (
                            <tr key={i} className="border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                              <td className="px-4 py-2.5" style={{ color: "var(--text-secondary)" }}>{t.date || "—"}</td>
                              <td className="px-4 py-2.5" style={{ color: "var(--text-primary)" }}>{t.description}</td>
                              <td className="px-4 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>{t.category}</td>
                              <td className="px-4 py-2.5 mono text-right" style={{ color: t.amount >= 0 ? "var(--success)" : "var(--danger)" }}>
                                {t.amount >= 0 ? "+" : ""}₹{t.amount.toLocaleString("en-IN")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="lg:col-span-1">
                    <div className="font-medium text-sm mb-4" style={{ color: "var(--text-primary)" }}>Ask about this document</div>
                    <div className="card flex flex-col" style={{ height: "420px" }}>
                      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
                        {chatMsgs.length === 0 && (
                          <div className="flex flex-col gap-2">
                            <div className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>Try asking:</div>
                            {["How much did I spend on food delivery?", "What was my biggest expense?", "What's my total spending this month?"].map((c) => (
                              <button key={c} onClick={() => sendQuestion(c)} className="text-left text-sm px-3 py-2 rounded-lg"
                                      style={{ background: "var(--accent-tint)", color: "var(--accent)" }}>
                                {c}
                              </button>
                            ))}
                          </div>
                        )}
                        {chatMsgs.map((m, i) => (
                          <div key={i} className="text-sm px-3 py-2 rounded-lg whitespace-pre-line"
                               style={{ background: m.role === "user" ? "var(--accent-tint)" : "var(--bg)",
                                        color: "var(--text-primary)", alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "92%" }}>
                            {m.text}
                          </div>
                        ))}
                        {chatLoading && <div className="text-sm" style={{ color: "var(--text-muted)" }}>Thinking…</div>}
                      </div>
                      <div className="border-t p-3 flex gap-2" style={{ borderColor: "var(--border)" }}>
                        <input value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                               onKeyDown={(e) => e.key === "Enter" && sendQuestion(chatInput)}
                               placeholder="Ask about this document…"
                               className="flex-1 text-sm px-3 py-2 rounded-lg outline-none" style={{ border: "1px solid var(--border-strong)" }} />
                        <button onClick={() => sendQuestion(chatInput)} disabled={chatLoading} className="btn-primary text-sm px-4 py-2">Ask</button>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
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
      <div className="text-xl font-semibold" style={{ color: accent ? "white" : color || "var(--text-primary)" }}>{value}</div>
    </div>
  );
}
