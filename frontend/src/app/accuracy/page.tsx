"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import type { BetHistoryResponse, BetResponse } from "@/types/api";
import { api, type ModelEvaluation, type MarketCalibration } from "@/lib/api";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ScatterChart,
  Scatter,
  Cell,
} from "recharts";

// ─── Data Processing Helpers ───────────────────────────────────────

function buildCalibrationData(bets: BetResponse[]) {
  const resolved = bets.filter((b) => b.result === "WIN" || b.result === "LOSS");
  if (resolved.length < 5) return [];

  const buckets: Record<string, { predicted: number; wins: number; total: number }> = {};
  const bucketSize = 0.1;

  for (const bet of resolved) {
    const prob = bet.model_probability;
    const bucketKey = (Math.floor(prob / bucketSize) * bucketSize).toFixed(1);
    if (!buckets[bucketKey]) {
      buckets[bucketKey] = { predicted: parseFloat(bucketKey) + bucketSize / 2, wins: 0, total: 0 };
    }
    buckets[bucketKey].total++;
    if (bet.result === "WIN") buckets[bucketKey].wins++;
  }

  return Object.values(buckets)
    .filter((b) => b.total >= 2)
    .map((b) => ({
      predicted: Math.round(b.predicted * 100),
      actual: Math.round((b.wins / b.total) * 100),
      count: b.total,
    }))
    .sort((a, b) => a.predicted - b.predicted);
}

function buildPnlTimeline(bets: BetResponse[]) {
  const resolved = bets
    .filter((b) => b.result && b.pnl !== null && b.pnl !== undefined)
    .sort((a, b) => new Date(a.placed_at).getTime() - new Date(b.placed_at).getTime());

  if (resolved.length === 0) return [];

  let cumPnl = 0;
  return resolved.map((bet, i) => {
    cumPnl += bet.pnl || 0;
    return {
      bet: i + 1,
      pnl: Math.round(cumPnl * 100) / 100,
      date: new Date(bet.placed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    };
  });
}

function buildEdgeRoiData(bets: BetResponse[]) {
  const resolved = bets.filter((b) => b.result && b.pnl !== null && b.pnl !== undefined);
  if (resolved.length < 3) return [];

  const thresholds = [3, 5, 6, 8, 10, 12, 15];
  return thresholds.map((t) => {
    const threshold = t / 100;
    const matching = resolved.filter((b) => b.edge_at_entry >= threshold);
    const wagered = matching.reduce((sum, b) => sum + b.amount_usd, 0);
    const pnl = matching.reduce((sum, b) => sum + (b.pnl || 0), 0);
    const roi = wagered > 0 ? (pnl / wagered) * 100 : 0;
    return { threshold: `≥${t}%`, roi: Math.round(roi * 10) / 10, count: matching.length };
  });
}

function buildMarketRoiData(bets: BetResponse[]) {
  const resolved = bets.filter((b) => b.result && b.pnl !== null && b.pnl !== undefined);
  if (resolved.length < 3) return [];

  const byType: Record<string, { wagered: number; pnl: number; count: number; wins: number }> = {};
  for (const bet of resolved) {
    const type = bet.market_type;
    if (!byType[type]) byType[type] = { wagered: 0, pnl: 0, count: 0, wins: 0 };
    byType[type].wagered += bet.amount_usd;
    byType[type].pnl += bet.pnl || 0;
    byType[type].count++;
    if (bet.result === "WIN") byType[type].wins++;
  }

  return Object.entries(byType).map(([type, data]) => ({
    type: type.charAt(0).toUpperCase() + type.slice(1),
    roi: data.wagered > 0 ? Math.round((data.pnl / data.wagered) * 1000) / 10 : 0,
    count: data.count,
    winRate: data.count > 0 ? Math.round((data.wins / data.count) * 100) : 0,
  }));
}

// ─── Chart Wrapper ─────────────────────────────────────────────────

function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
      <h3 className="text-sm font-semibold text-[#e2e8f0] mb-0.5">{title}</h3>
      {subtitle && <p className="text-xs text-[#64748b] mb-3">{subtitle}</p>}
      <div className="h-56">{children}</div>
    </div>
  );
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="h-full flex items-center justify-center text-[#475569] text-sm">
      {message}
    </div>
  );
}

// ─── Model vs Market ───────────────────────────────────────────────

const CONCLUSION_TEXT: Record<MarketCalibration["conclusion"], { label: string; color: string }> = {
  too_few: { label: "Too few to conclude", color: "#64748b" },
  model_better: { label: "Model beats market", color: "#4CAF50" },
  market_better: { label: "Market beats model", color: "#FF1744" },
  no_difference: { label: "No significant difference", color: "#FFB300" },
};

const fmt = (v: number | null, digits = 3) => (v === null ? "—" : v.toFixed(digits));
const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
const signed = (v: number | null, digits = 3) => (v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`);
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function ModelVsMarket({ evaluation }: { evaluation: ModelEvaluation }) {
  const { graded_games, min_games, conclusive } = evaluation;
  const th = "text-left font-medium text-[#64748b] py-1.5 pr-4";
  const td = "py-1.5 pr-4 text-[#e2e8f0] tabular-nums";

  return (
    <section className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 mb-6">
      <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
        <h2 className="text-sm font-semibold text-[#e2e8f0]">Model vs Market</h2>
        <span className="text-xs text-[#64748b]">
          {graded_games} graded games over {evaluation.dates.length}{" "}
          {evaluation.dates.length === 1 ? "date" : "dates"} · prices locked at tip-off
        </span>
      </div>
      <p className="text-xs text-[#64748b] mb-3">
        Brier score / log loss of the model probability vs the Polymarket price for the same side (lower is better).
        Big edges are only real if the model beats the market here.
      </p>

      {!conclusive && (
        <div className="bg-[#FFB300]/10 border border-[#FFB300]/30 rounded-md p-3 mb-4">
          <p className="text-sm text-[#FFB300] font-medium">
            {graded_games} {graded_games === 1 ? "game" : "games"} — too few to conclude
          </p>
          <p className="text-xs text-[#FFB300]/80 mt-0.5">
            Need ~{min_games} graded games before these numbers say anything about whether edges are real.
            Differences below are noise until then.
          </p>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs mb-4">
          <thead>
            <tr className="border-b border-[#1e293b]">
              <th className={th}>Market</th>
              <th className={th}>N</th>
              <th className={th}>Brier model</th>
              <th className={th}>Brier market</th>
              <th className={th}>Log loss model</th>
              <th className={th}>Log loss market</th>
              <th className={th}>Model − market (±SE)</th>
              <th className={th}>Avg disagreement</th>
              <th className={th}>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {evaluation.calibration.map((c) => (
              <tr key={c.market_type} className="border-b border-[#1e293b]/50">
                <td className={td}>{title(c.market_type)}</td>
                <td className={td}>{c.n}</td>
                <td className={td}>{fmt(c.model_brier)}</td>
                <td className={td}>{fmt(c.market_brier)}</td>
                <td className={td}>{fmt(c.model_log_loss)}</td>
                <td className={td}>{fmt(c.market_log_loss)}</td>
                <td className={td}>
                  {signed(c.brier_diff)}
                  {c.brier_diff_se !== null && <span className="text-[#64748b]"> ±{c.brier_diff_se.toFixed(3)}</span>}
                </td>
                <td className={td}>{pct(c.avg_abs_disagreement)}</td>
                <td className="py-1.5" style={{ color: CONCLUSION_TEXT[c.conclusion].color }}>
                  {CONCLUSION_TEXT[c.conclusion].label}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className="text-xs font-semibold text-[#e2e8f0] mb-1">BUY / STRONG BUY verdicts — flat $1 at saved price</h3>
        <table className="w-full text-xs mb-4">
          <thead>
            <tr className="border-b border-[#1e293b]">
              <th className={th}>Market</th>
              <th className={th}>Bets</th>
              <th className={th}>Hit rate</th>
              <th className={th}>Break-even</th>
              <th className={th}>P&L</th>
              <th className={th}>ROI (±SE)</th>
            </tr>
          </thead>
          <tbody>
            {evaluation.bets.map((b) => (
              <tr key={b.market_type} className="border-b border-[#1e293b]/50">
                <td className={td}>{b.market_type === "all" ? "All" : title(b.market_type)}</td>
                <td className={td}>{b.n === 0 ? "0" : `${b.wins}/${b.n}`}</td>
                <td className={td}>{pct(b.hit_rate)}</td>
                <td className={td}>{pct(b.avg_price)}</td>
                <td className={td} style={{ color: b.pnl >= 0 ? "#4CAF50" : "#FF1744" }}>
                  {b.n === 0 ? "—" : `${b.pnl >= 0 ? "+" : "−"}$${Math.abs(b.pnl).toFixed(2)}`}
                </td>
                <td className={td}>
                  {b.roi === null ? "—" : `${b.roi >= 0 ? "+" : ""}${(b.roi * 100).toFixed(1)}%`}
                  {b.roi_se !== null && <span className="text-[#64748b]"> ±{(b.roi_se * 100).toFixed(1)}%</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-xs text-[#64748b] border-t border-[#1e293b] pt-3">
        <span className="font-medium text-[#94a3b8]">Closing-line value: </span>
        {evaluation.clv.supported ? "available" : (
          <>
            not measurable yet. {evaluation.clv.reason} <span className="text-[#94a3b8]">Needed:</span>{" "}
            {evaluation.clv.needed}
          </>
        )}
      </div>
    </section>
  );
}

// Shared tooltip style
const tooltipStyle = { background: "#1a2235", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 };

// ─── Main Page ─────────────────────────────────────────────────────

export default function ModelAccuracy() {
  const [history, setHistory] = useState<BetHistoryResponse | null>(null);
  const [evaluation, setEvaluation] = useState<ModelEvaluation | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    // Grading fetches final scores per date — don't hold the bet charts on it.
    api.getModelEvaluation().then(setEvaluation, () => setEvaluation(null));
    try {
      const data = await api.getBetHistory();
      setHistory(data);
    } catch {
      // Silently fail — show empty states
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const bets = history?.bets || [];
  const resolvedCount = bets.filter((b) => b.result === "WIN" || b.result === "LOSS").length;
  const calibrationData = buildCalibrationData(bets);
  const pnlData = buildPnlTimeline(bets);
  const edgeRoiData = buildEdgeRoiData(bets);
  const marketRoiData = buildMarketRoiData(bets);

  const minBetsNeeded = 10;
  const hasEnoughData = resolvedCount >= minBetsNeeded;

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-[#e2e8f0]">Model Accuracy</h1>
            <p className="text-xs text-[#64748b] mt-0.5">
              {resolvedCount} resolved bets
              {resolvedCount < minBetsNeeded && ` — need ${minBetsNeeded - resolvedCount} more for charts`}
            </p>
          </div>
          {loading && (
            <div className="w-5 h-5 border-2 border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin" />
          )}
        </div>

        {evaluation && <ModelVsMarket evaluation={evaluation} />}

        {!loading && !hasEnoughData && (
          <div className="bg-[#2979FF]/10 border border-[#2979FF]/20 rounded-lg p-4 mb-6">
            <p className="text-sm text-[#2979FF]">
              Charts will populate after {minBetsNeeded}+ resolved bets. Keep logging bets from the dashboard!
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Calibration Curve */}
          <ChartCard title="Calibration Curve" subtitle="Predicted probability vs actual win rate">
            {calibrationData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 5, right: 20, bottom: 20, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="predicted" name="Predicted" unit="%" type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis dataKey="actual" name="Actual" unit="%" type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="#334155" strokeDasharray="4 4" />
                  <Scatter data={calibrationData} fill="#2979FF">
                    {calibrationData.map((entry, i) => (
                      <Cell key={i} fill={Math.abs(entry.predicted - entry.actual) <= 10 ? "#4CAF50" : "#FF1744"} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="Need 5+ resolved bets with varied probabilities" />
            )}
          </ChartCard>

          {/* Cumulative P&L */}
          <ChartCard title="Cumulative P&L" subtitle="Running profit/loss over time">
            {pnlData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={pnlData} margin={{ top: 5, right: 20, bottom: 20, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="bet" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `Bet #${v}`} />
                  <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="pnl" stroke="#2979FF" strokeWidth={2} dot={{ r: 3, fill: "#2979FF" }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="Need resolved bets with P&L data" />
            )}
          </ChartCard>

          {/* ROI by Edge Threshold */}
          <ChartCard title="ROI by Edge Threshold" subtitle="Higher edge → better expected returns">
            {edgeRoiData.length > 0 && edgeRoiData.some((d) => d.count > 0) ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={edgeRoiData} margin={{ top: 5, right: 20, bottom: 20, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="threshold" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 4" />
                  <Bar dataKey="roi" radius={[4, 4, 0, 0]}>
                    {edgeRoiData.map((entry, i) => (
                      <Cell key={i} fill={entry.roi >= 0 ? "#4CAF50" : "#FF1744"} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="Need 3+ resolved bets to calculate ROI" />
            )}
          </ChartCard>

          {/* ROI by Market Type */}
          <ChartCard title="ROI by Market Type" subtitle="Spread vs Moneyline vs Total performance">
            {marketRoiData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={marketRoiData} margin={{ top: 5, right: 20, bottom: 20, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="type" tick={{ fontSize: 11, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 4" />
                  <Bar dataKey="roi" radius={[4, 4, 0, 0]}>
                    {marketRoiData.map((entry, i) => (
                      <Cell key={i} fill={entry.roi >= 0 ? "#4CAF50" : "#FF1744"} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="Need 3+ resolved bets across market types" />
            )}
          </ChartCard>
        </div>
      </main>
    </div>
  );
}
