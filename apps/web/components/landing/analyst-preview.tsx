"use client";

import { useState } from "react";
import { BadgeCheck, Bot, ChevronRight, Database, Sparkles } from "lucide-react";
import { SQLViewer } from "@/components/common/sql-viewer";

const SQL = `SELECT
  DATE_TRUNC('month', order_date) AS month,
  SUM(total_amount) AS revenue
FROM ds_retail
WHERE order_date >= '2026-01-01'
GROUP BY 1
ORDER BY 1;`;

export function AnalystPreview() {
  const [active, setActive] = useState(0);
  const questions = [
    "Why did revenue decrease in the last quarter?",
    "Which region performs best?",
    "What does average order value mean?",
  ];

  return (
    <div className="glass overflow-hidden rounded-3xl border-line/12">
      <div className="flex items-center justify-between border-b border-line/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-gradient text-white">
            <Bot className="h-3.5 w-3.5" />
          </span>
          <div>
            <p className="text-[12px] font-semibold text-ink">AI analyst</p>
            <p className="text-[10px] text-faint">Retail sales · approved semantic model</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-success/25 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
          <BadgeCheck className="h-3 w-3" /> Verified
        </span>
      </div>

      <div className="space-y-3 p-4">
        <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-brand px-3.5 py-2 text-[12.5px] text-white shadow-[0_10px_24px_-16px_rgba(79,107,255,0.9)]">
          {questions[active]}
        </div>

        <div className="max-w-[92%] space-y-2.5">
          <div className="rounded-2xl rounded-bl-md border border-line/10 bg-surface/70 px-3.5 py-2.5">
            <p className="text-[12.5px] leading-relaxed text-ink">
              {active === 0 ? (
                <>
                  Revenue fell <span className="font-semibold">21.8%</span> to <span className="font-semibold">₹319,944</span> in the
                  latest quarter. The largest decline came from the <span className="font-semibold">West</span> region
                  (−₹89,438), where average discount rose.
                </>
              ) : active === 1 ? (
                <>
                  <span className="font-semibold">North</span> leads with <span className="font-semibold">₹841,665</span> (30.3% of
                  total revenue). West is lowest at ₹585,843.
                </>
              ) : (
                <>
                  <span className="font-semibold">Average order value</span> is total revenue divided by distinct orders. For this
                  dataset the definition awaits approval before it is used as a headline KPI.
                </>
              )}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="metric-pill"><Database className="h-3 w-3" /> 1 query</span>
              <span className="metric-pill"><BadgeCheck className="h-3 w-3 text-success" /> grounded</span>
              <span className="metric-pill"><Sparkles className="h-3 w-3 text-violet" /> Gemini</span>
            </div>
          </div>
          {active !== 2 && <SQLViewer sql={SQL} label="View generated SQL" />}
        </div>

        <div className="flex flex-wrap gap-1.5 pt-1">
          {questions.map((question, index) => (
            <button
              key={question}
              type="button"
              onClick={() => setActive(index)}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition ${
                active === index
                  ? "border-brand/40 bg-brand/10 text-brand"
                  : "border-line/12 bg-surface/50 text-muted hover:border-line/25 hover:text-ink"
              }`}
            >
              {question}
              <ChevronRight className="h-3 w-3" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
