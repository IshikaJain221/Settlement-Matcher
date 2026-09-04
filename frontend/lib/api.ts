// Central API client — the only place the frontend talks to the backend.
// Mirrors the Repository pattern used on the backend: one seam, easy to swap.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface Stats {
  total_orders: number;
  matched_rule: number;
  matched_ai: number;
  unresolved: number;
  unknown_settlements: number;
  match_rate_pct: number;
  rule_resolution_pct: number;
  ai_assist_pct: number;
}

export interface Record_ {
  order_id: string;
  customer: string;
  order_amount: number;
  order_date: string;
  settlement_utr: string | null;
  settlement_amount: number | null;
  settlement_date: string | null;
  status: "matched_rule" | "matched_ai" | "unresolved";
  exception_type: string;
  reason: string;
  confidence: number;
  resolved_by: string;
  scenario?: string;
}

export interface UnknownSettlement {
  utr: string;
  order_ref: string;
  amount: number;
  settlement_date: string;
  reason: string;
  exception_type: string;
}

export async function runMatch(scenario: string = "original"): Promise<{ message: string; scenario: string; total_records: number }> {
  const res = await fetch(`${API_BASE}/api/match/run?scenario=${scenario}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to run matching pipeline");
  return res.json();
}

export async function getStats(scenario: string = "original"): Promise<Stats> {
  const res = await fetch(`${API_BASE}/api/stats?scenario=${scenario}`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function getRecords(scenario: string = "original"): Promise<{ records: Record_[]; unknown_settlements: UnknownSettlement[] }> {
  const res = await fetch(`${API_BASE}/api/records?scenario=${scenario}`);
  if (!res.ok) throw new Error("Failed to fetch records");
  return res.json();
}

export async function askQuestion(question: string, scenario: string = "original"): Promise<{ answer: string; sources: Record_[] }> {
  const res = await fetch(`${API_BASE}/api/qa?scenario=${scenario}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error("Failed to get answer");
  return res.json();
}

export interface Scenario {
  key: string;
  label: string;
  description: string;
}

export async function getScenarios(): Promise<{ scenarios: Scenario[] }> {
  const res = await fetch(`${API_BASE}/api/scenarios`);
  if (!res.ok) throw new Error("Failed to fetch scenarios");
  return res.json();
}

export async function getSuggestions(scenario: string): Promise<{ suggestions: string[] }> {
  const res = await fetch(`${API_BASE}/api/qa/suggestions?scenario=${scenario}`);
  if (!res.ok) throw new Error("Failed to fetch suggestions");
  return res.json();
}

// -------------------- documents (RAG) --------------------

export interface Transaction {
  date: string;
  description: string;
  amount: number;
  category: string;
}

export interface DocAnalysis {
  total_transactions: number;
  total_in: number;
  total_out: number;
  net: number;
  category_breakdown: { category: string; amount: number }[];
  monthly_trend: { month: string; net: number }[];
  top_transactions: Transaction[];
}

export async function uploadDocument(file: File): Promise<{ doc_id: string; filename: string; chunk_count: number; embedding_method: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/documents/upload`, { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function chatWithDocument(docId: string, question: string): Promise<{ answer: string; retrieval_method: string; chunks_used: number }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error("Failed to get answer");
  return res.json();
}

export async function getDocAnalysis(docId: string): Promise<{ analysis: DocAnalysis; transactions: Transaction[]; extraction_method: string }> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/analysis`);
  if (!res.ok) throw new Error("Failed to get analysis");
  return res.json();
}
