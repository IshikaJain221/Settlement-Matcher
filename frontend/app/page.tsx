"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { AnimatedCounter, FadeUp } from "@/components/AnimatedCounter";

const steps = [
  { n: "01", title: "Two records arrive", body: "Internal order records and bank settlement records — two lists that should agree, but often don't." },
  { n: "02", title: "Rules match the easy cases", body: "Amount and date checks resolve most records instantly — no AI needed for the obvious matches." },
  { n: "03", title: "AI resolves the tricky ones", body: "Leftover cases — fees, delays, duplicates — get a reasoned match or an honest exception label." },
  { n: "04", title: "Ask questions, see the score", body: "Chat with the exceptions directly, and see match rate, AI-assist rate, and what's still unresolved." },
];

const features = [
  { title: "Rule-based matching", body: "Fast, deterministic checks handle amount and date agreement before any AI is involved." },
  { title: "AI-assisted resolution", body: "Fee deductions, delayed settlements, and duplicate entries get reasoned, explained matches." },
  { title: "Honest exception list", body: "Unresolved records are never hidden — every one gets a plain-English reason." },
  { title: "Grounded Q&A", body: "Ask about any order or exception and get an answer sourced from the actual data." },
];

const scenarios = [
  { title: "Discount / Coupon", body: "Bought at 30% off — did the bank actually charge the discounted price?" },
  { title: "Refund / Reversal", body: "Refund approved internally — did the money actually reverse?" },
  { title: "Split Payment", body: "Card + wallet — did both legs settle, and do they sum correctly?" },
  { title: "Subscription Billing", body: "Renewal charged — at the right plan price, not a stale one?" },
  { title: "Tax / GST", body: "Was 18% GST actually applied, or was it silently dropped?" },
];

export default function Home() {
  return (
    <div style={{ minHeight: "100vh", overflow: "hidden" }}>
      <nav className="border-b" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-semibold" style={{ background: "var(--accent)" }}>SM</div>
            <span className="font-semibold text-[15px]" style={{ color: "var(--text-primary)" }}>Settlement Matcher</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="btn-primary text-sm px-4 py-2">Open dashboard</Link>
            <Link href="/documents" className="btn-secondary text-sm px-4 py-2">Analyze a document</Link>
          </div>
        </div>
      </nav>

      {/* Hero with animated gradient blob */}
      <section className="max-w-6xl mx-auto px-6 pt-20 pb-16 relative">
        <motion.div
          aria-hidden
          style={{
            position: "absolute", top: -80, right: -120, width: 480, height: 480,
            borderRadius: "50%", background: "radial-gradient(circle, var(--accent-tint) 0%, transparent 70%)",
            zIndex: 0, pointerEvents: "none",
          }}
          animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="max-w-2xl relative"
          style={{ zIndex: 1 }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full mb-6"
            style={{ background: "var(--accent-tint)", color: "var(--accent)" }}
          >
            Razorpay AI Buildathon 2026 — Track 04
          </motion.div>
          <h1 className="text-[44px] leading-[1.1] font-semibold tracking-tight mb-5" style={{ color: "var(--text-primary)" }}>
            Reconcile settlements without reading a single row by hand.
          </h1>
          <p className="text-lg mb-8" style={{ color: "var(--text-secondary)" }}>
            Settlement Matcher compares internal order records against bank settlements,
            resolves what it can automatically, and explains — honestly — what it can&apos;t.
          </p>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="btn-primary text-sm px-5 py-3">Run reconciliation →</Link>
            <a href="#how-it-works" className="btn-secondary text-sm px-5 py-3">See how it works</a>
          </div>

          {/* Animated stat strip */}
          <div className="flex items-center gap-8 mt-12">
            <div>
              <div className="text-2xl font-semibold" style={{ color: "var(--accent)" }}>
                <AnimatedCounter target={93.8} suffix="%" />
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>match rate</div>
            </div>
            <div>
              <div className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                <AnimatedCounter target={6} />
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>mismatch scenarios</div>
            </div>
            <div>
              <div className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                <AnimatedCounter target={340} />
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>records reconciled</div>
            </div>
          </div>
        </motion.div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16" id="how-it-works">
        <FadeUp>
          <h2 className="text-2xl font-semibold mb-2" style={{ color: "var(--text-primary)" }}>How it works</h2>
          <p className="mb-10" style={{ color: "var(--text-secondary)" }}>One closed loop — ingest, match, explain, report.</p>
        </FadeUp>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
          {steps.map((s, i) => (
            <FadeUp key={s.n} delay={i * 0.08}>
              <div className="card p-5 h-full">
                <div className="mono text-xs font-medium mb-3" style={{ color: "var(--accent)" }}>{s.n}</div>
                <div className="font-medium text-[15px] mb-2" style={{ color: "var(--text-primary)" }}>{s.title}</div>
                <div className="text-sm" style={{ color: "var(--text-secondary)" }}>{s.body}</div>
              </div>
            </FadeUp>
          ))}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16">
        <FadeUp>
          <h2 className="text-2xl font-semibold mb-2" style={{ color: "var(--text-primary)" }}>Six mismatch scenarios, one engine</h2>
          <p className="mb-10" style={{ color: "var(--text-secondary)" }}>Real reconciliation problems aren&apos;t all the same shape — so neither is the test data.</p>
        </FadeUp>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {scenarios.map((s, i) => (
            <FadeUp key={s.title} delay={i * 0.06}>
              <div className="card p-4 h-full">
                <div className="font-medium text-sm mb-1.5" style={{ color: "var(--text-primary)" }}>{s.title}</div>
                <div className="text-xs" style={{ color: "var(--text-secondary)" }}>{s.body}</div>
              </div>
            </FadeUp>
          ))}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16">
        <FadeUp>
          <h2 className="text-2xl font-semibold mb-10" style={{ color: "var(--text-primary)" }}>Built for honest numbers, not a polished demo</h2>
        </FadeUp>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {features.map((f, i) => (
            <FadeUp key={f.title} delay={i * 0.07}>
              <div className="card p-6 h-full">
                <div className="font-medium text-[15px] mb-2" style={{ color: "var(--text-primary)" }}>{f.title}</div>
                <div className="text-sm" style={{ color: "var(--text-secondary)" }}>{f.body}</div>
              </div>
            </FadeUp>
          ))}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20">
        <FadeUp>
          <div className="card p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6" style={{ background: "var(--accent-tint)", borderColor: "var(--accent-tint)" }}>
            <div>
              <div className="font-semibold text-xl mb-1" style={{ color: "var(--text-primary)" }}>See it match real records</div>
              <div className="text-sm" style={{ color: "var(--text-secondary)" }}>6 switchable datasets, real mismatches, live on the dashboard.</div>
            </div>
            <Link href="/dashboard" className="btn-primary text-sm px-5 py-3 whitespace-nowrap">Open dashboard →</Link>
          </div>
        </FadeUp>
      </section>

      <footer className="border-t py-8" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 text-sm" style={{ color: "var(--text-muted)" }}>
          Settlement Matcher — built for the Razorpay AI Builder Internship 2026.
        </div>
      </footer>
    </div>
  );
}
