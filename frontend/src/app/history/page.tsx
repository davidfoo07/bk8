"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import { formatPct } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface GameResult {
  game_id: string;
  away_team: string;
  home_team: string;
  model_home_win_prob: number;
  model_spread: number;
  model_total: number;
  favored_team: string;
  favored_prob: number;
  poly_spread_line: number | null;
  poly_spread_team: string | null;
  poly_total_line: number | null;
  home_score: number | null;
  away_score: number | null;
  actual_total: number | null;
  actual_margin: number | null;
  winner: string | null;
  ml_correct: boolean | null;
  spread_cover_correct: boolean | null;
  total_ou_correct: boolean | null;
  spread_error: number | null;
  total_error: number | null;
  status: string;
}

interface DailyResults {
  date: string;
  games: GameResult[];
  ml_record: string;
  ml_accuracy: number | null;
  spread_record: string;
  spread_accuracy: number | null;
  ou_record: string;
  ou_accuracy: number | null;
  avg_total_error: number | null;
  avg_spread_error: number | null;
  total_bias: number | null;
}

interface SavedDate {
  date: string;
  games_count: number;
  saved_at: string | null;
}

/** Color by error magnitude */
function errColor(err: number, good: number, ok: number): string {
  const a = Math.abs(err);
  if (a <= good) return "text-[#00C853]";
  if (a <= ok) return "text-[#FFD600]";
  return "text-[#FF1744]";
}

/** Accuracy badge color */
function accColor(acc: number | null): string {
  if (acc == null) return "#64748b";
  if (acc >= 0.6) return "#00C853";
  if (acc >= 0.5) return "#FFD600";
  return "#FF1744";
}

/** ✓ or ✗ */
function Grade({ val }: { val: boolean | null }) {
  if (val === true) return <span className="text-[#00C853] font-bold">✓</span>;
  if (val === false) return <span className="text-[#FF1744] font-bold">✗</span>;
  return <span className="text-[#475569]">—</span>;
}

export default function HistoryPage() {
  const [dates, setDates] = useState<SavedDate[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [results, setResults] = useState<DailyResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/results/`)
      .then((r) => r.json())
      .then((data: SavedDate[]) => {
        setDates(data);
        if (data.length > 0) setSelectedDate(data[0].date);
      })
      .catch((e) => setError(e.message));
  }, []);

  const loadResults = useCallback(async (dateStr: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/results/${dateStr}`);
      if (!res.ok) throw new Error(`Failed to load: ${res.status}`);
      setResults(await res.json());
    } catch (e) {
      setError((e as Error).message);
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDate) loadResults(selectedDate);
  }, [selectedDate, loadResults]);

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e2e8f0]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Header row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold">Prediction Results</h2>
            <p className="text-sm text-[#94a3b8] mt-1">
              Model predictions vs actual NBA results — side by side
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-[#64748b]">Date:</span>
            <select
              value={selectedDate || ""}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-[#1a2235] border border-[#334155] rounded px-3 py-1.5 text-sm text-[#e2e8f0] font-mono focus:outline-none focus:border-[#2979FF]"
            >
              {dates.map((d) => (
                <option key={d.date} value={d.date}>
                  {d.date} ({d.games_count} games)
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg text-[#FF1744] text-sm mb-6">{error}</div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-20 text-[#94a3b8]">
            <svg className="animate-spin h-6 w-6 mr-3 text-[#2979FF]" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Loading results...
          </div>
        )}

        {results && !loading && (
          <>
            {/* ── Summary Cards ── */}
            <div className="grid grid-cols-7 gap-3 mb-8">
              <StatCard label="ML Record" value={results.ml_record} sub={results.ml_accuracy != null ? `${(results.ml_accuracy * 100).toFixed(0)}%` : undefined} color={accColor(results.ml_accuracy)} />
              <StatCard label="Spread Record" value={results.spread_record} sub={results.spread_accuracy != null ? `${(results.spread_accuracy * 100).toFixed(0)}%` : "No lines"} color={accColor(results.spread_accuracy)} />
              <StatCard label="O/U Record" value={results.ou_record} sub={results.ou_accuracy != null ? `${(results.ou_accuracy * 100).toFixed(0)}%` : "No lines"} color={accColor(results.ou_accuracy)} />
              <StatCard label="Total MAE" value={results.avg_total_error != null ? `${results.avg_total_error.toFixed(1)}` : "—"} sub="pts" color={results.avg_total_error != null && results.avg_total_error <= 10 ? "#00C853" : results.avg_total_error != null && results.avg_total_error <= 15 ? "#FFD600" : "#FF1744"} />
              <StatCard label="Total Bias" value={results.total_bias != null ? `${results.total_bias > 0 ? "+" : ""}${results.total_bias.toFixed(1)}` : "—"} sub={results.total_bias != null ? (results.total_bias > 0 ? "Under" : "Over") : undefined} color={results.total_bias != null && Math.abs(results.total_bias) <= 5 ? "#00C853" : "#FFD600"} />
              <StatCard label="Spread MAE" value={results.avg_spread_error != null ? `${results.avg_spread_error.toFixed(1)}` : "—"} sub="pts" color={results.avg_spread_error != null && results.avg_spread_error <= 8 ? "#00C853" : results.avg_spread_error != null && results.avg_spread_error <= 12 ? "#FFD600" : "#FF1744"} />
              <StatCard label="Games" value={`${results.games.filter((g) => g.status === "FINAL").length}/${results.games.length}`} sub="Final" color="#2979FF" />
            </div>

            {/* ── Results Table ── */}
            <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="bg-[#1a2235] text-[10px] text-[#64748b] uppercase">
                      <th className="text-left py-2.5 px-3">Game</th>
                      <th className="text-center py-2.5 px-2">Score</th>
                      {/* ML group */}
                      <th className="text-right py-2.5 px-2 border-l border-[#1e293b]">Model Pick</th>
                      <th className="text-right py-2.5 px-2">Winner</th>
                      <th className="text-center py-2.5 px-1">✓</th>
                      {/* Spread group */}
                      <th className="text-right py-2.5 px-2 border-l border-[#1e293b]">
                        <span className="text-[#2979FF]">Pred</span> Spread
                      </th>
                      <th className="text-right py-2.5 px-2">
                        <span className="text-[#7C4DFF]">Poly</span> Line
                      </th>
                      <th className="text-right py-2.5 px-2">
                        <span className="text-[#e2e8f0]">Actual</span> Margin
                      </th>
                      <th className="text-center py-2.5 px-1">✓</th>
                      <th className="text-right py-2.5 px-1">Err</th>
                      {/* Total group */}
                      <th className="text-right py-2.5 px-2 border-l border-[#1e293b]">
                        <span className="text-[#2979FF]">Pred</span> Total
                      </th>
                      <th className="text-right py-2.5 px-2">
                        <span className="text-[#7C4DFF]">Poly</span> O/U
                      </th>
                      <th className="text-right py-2.5 px-2">
                        <span className="text-[#e2e8f0]">Actual</span>
                      </th>
                      <th className="text-center py-2.5 px-1">✓</th>
                      <th className="text-right py-2.5 px-2">Err</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.games.map((g) => {
                      const fin = g.status === "FINAL";

                      return (
                        <tr key={g.game_id} className="border-t border-[#1e293b] hover:bg-[#1a2235]/50">
                          {/* Game */}
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-[#e2e8f0] whitespace-nowrap">{g.away_team} @ {g.home_team}</span>
                              <StatusBadge status={g.status} />
                            </div>
                          </td>

                          {/* Score */}
                          <td className="py-2.5 px-2 text-center font-mono font-semibold whitespace-nowrap">
                            {fin && g.away_score != null && g.home_score != null ? (
                              <>
                                <span className={g.winner === g.away_team ? "text-[#00C853]" : "text-[#94a3b8]"}>{g.away_score}</span>
                                <span className="text-[#475569] mx-0.5">-</span>
                                <span className={g.winner === g.home_team ? "text-[#00C853]" : "text-[#94a3b8]"}>{g.home_score}</span>
                              </>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>

                          {/* ── ML: Model Pick vs Winner ── */}
                          <td className="py-2.5 px-2 text-right font-mono border-l border-[#1e293b] whitespace-nowrap">
                            <span className="text-[#2979FF]">{g.favored_team}</span>
                            <span className="text-[#64748b] ml-1 text-[11px]">{formatPct(g.favored_prob)}</span>
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono whitespace-nowrap">
                            {fin && g.winner ? (
                              <span className="text-[#e2e8f0] font-semibold">{g.winner}</span>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                          <td className="py-2.5 px-1 text-center"><Grade val={g.ml_correct} /></td>

                          {/* ── Spread: Pred | Poly Line | Actual | ✓ | Err ── */}
                          <td className="py-2.5 px-2 text-right font-mono text-[#2979FF] border-l border-[#1e293b] whitespace-nowrap">
                            {g.home_team} {g.model_spread > 0 ? "+" : ""}{g.model_spread.toFixed(1)}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono text-[#7C4DFF] whitespace-nowrap">
                            {g.poly_spread_line != null ? (
                              <>{g.home_team} {g.poly_spread_line > 0 ? "+" : ""}{g.poly_spread_line}</>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono whitespace-nowrap">
                            {fin && g.actual_margin != null ? (
                              <span className="text-[#e2e8f0]">{g.home_team} {g.actual_margin > 0 ? "+" : ""}{g.actual_margin}</span>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                          <td className="py-2.5 px-1 text-center"><Grade val={g.spread_cover_correct} /></td>
                          <td className="py-2.5 px-1 text-right font-mono text-[11px]">
                            {g.spread_error != null ? (
                              <span className={errColor(g.spread_error, 6, 12)}>{g.spread_error.toFixed(1)}</span>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>

                          {/* ── Total: Pred | Poly O/U | Actual | ✓ | Err ── */}
                          <td className="py-2.5 px-2 text-right font-mono text-[#2979FF] border-l border-[#1e293b]">
                            {g.model_total.toFixed(1)}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono text-[#7C4DFF]">
                            {g.poly_total_line != null ? (
                              <>O/U {g.poly_total_line}</>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono">
                            {fin && g.actual_total != null ? (
                              <span className="text-[#e2e8f0] font-semibold">{g.actual_total}</span>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                          <td className="py-2.5 px-1 text-center"><Grade val={g.total_ou_correct} /></td>
                          <td className="py-2.5 px-2 text-right font-mono text-[11px]">
                            {g.total_error != null ? (
                              <span className={errColor(g.total_error, 8, 15)}>
                                {g.total_error > 0 ? "+" : ""}{g.total_error.toFixed(1)}
                              </span>
                            ) : <span className="text-[#475569]">—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-[#64748b]">
              <span><span className="text-[#2979FF]">Blue</span> = model prediction</span>
              <span><span className="text-[#7C4DFF]">Purple</span> = Polymarket line</span>
              <span>Spread ✓ = model&apos;s side covered against Poly line</span>
              <span>O/U ✓ = model&apos;s Over/Under call vs Poly line correct</span>
              <span>Total Err is signed: + = under-predicted</span>
            </div>
          </>
        )}

        {!results && !loading && !error && dates.length === 0 && (
          <div className="text-center py-20 text-[#64748b]">
            <p className="text-lg mb-2">No saved predictions yet</p>
            <p className="text-sm">Predictions are saved automatically when the pipeline runs. Check back after game day.</p>
          </div>
        )}
      </main>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color: string }) {
  return (
    <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-3">
      <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-bold font-mono" style={{ color }}>{value}</p>
      {sub && <p className="text-[10px] text-[#64748b] mt-0.5">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "FINAL") {
    return <span className="text-[9px] px-1 py-0.5 rounded bg-[#64748b]/15 text-[#94a3b8] border border-[#64748b]/30 font-medium">FINAL</span>;
  }
  if (status === "LIVE") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] px-1 py-0.5 rounded bg-[#FF1744]/15 text-[#FF1744] border border-[#FF1744]/30 font-semibold">
        <span className="relative flex h-1.5 w-1.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#FF1744] opacity-75" /><span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#FF1744]" /></span>
        LIVE
      </span>
    );
  }
  return <span className="text-[9px] px-1 py-0.5 rounded bg-[#2979FF]/15 text-[#2979FF] border border-[#2979FF]/30 font-medium">SCHED</span>;
}
