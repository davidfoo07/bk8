"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import Header from "@/components/Header";
import TopEdges from "@/components/TopEdges";
import GameCard from "@/components/GameCard";
import EmptyState from "@/components/EmptyState";
import type { DailyAnalysis, GameAnalysis } from "@/types/api";
import { api } from "@/lib/api";
import { copyToClipboard, formatPct, formatET, formatSGT, getVerdictBg, formatEdge } from "@/lib/utils";

const AUTO_REFRESH_MS = 5 * 60 * 1000;
const LIVE_REFRESH_MS = 30 * 1000;

/** Scroll to a game card by game_id and flash highlight it */
function scrollToGame(gameId: string) {
  const el = document.getElementById(`game-${gameId}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("ring-2", "ring-[#2979FF]");
    setTimeout(() => el.classList.remove("ring-2", "ring-[#2979FF]"), 2000);
  }
}

/** Get the favored team + prob from a game */
function getFavored(g: GameAnalysis) {
  if (g.model.home_win_prob >= 0.5) return { name: g.home.team, prob: g.model.home_win_prob };
  return { name: g.away.team, prob: 1 - g.model.home_win_prob };
}

/** Get the best edge from a game's markets */
function getBestEdge(g: GameAnalysis) {
  const entries = Object.values(g.markets);
  if (entries.length === 0) return null;
  return entries.reduce((best, m) => (m.edge.best_edge > (best?.edge.best_edge || 0) ? m : best), entries[0]);
}

export default function Dashboard() {
  const [data, setData] = useState<DailyAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiPromptCopied, setAiPromptCopied] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [expandedGameId, setExpandedGameId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [injuryOverrides, setInjuryOverrides] = useState<Record<string, string>>({});
  const overridesRef = useRef<Record<string, string>>({});
  overridesRef.current = injuryOverrides;

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const overrides = overridesRef.current;
      const hasOverrides = Object.keys(overrides).length > 0;
      const result = hasOverrides
        ? await api.getTodaysGamesWithOverrides(overrides)
        : await api.getTodaysGames();
      setData(result);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load data";
      setError(message);
      if (!isRefresh) setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    timerRef.current = setInterval(() => loadData(true), AUTO_REFRESH_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loadData]);

  useEffect(() => {
    const hasLiveGame = data?.games?.some((g) => g.live?.game_status === 2);
    if (timerRef.current) clearInterval(timerRef.current);
    const interval = hasLiveGame ? LIVE_REFRESH_MS : AUTO_REFRESH_MS;
    timerRef.current = setInterval(() => loadData(true), interval);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [data, loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/games/refresh`, { method: "POST" });
    } catch { /* ignore */ }
    setInjuryOverrides({});
    overridesRef.current = {};
    await loadData(true);
  };

  const handleInjuryToggle = useCallback((playerName: string, mode: "FULL" | "HALF" | "OFF") => {
    setInjuryOverrides((prev) => {
      const next = { ...prev };
      if (mode === "HALF") { delete next[playerName]; } else { next[playerName] = mode; }
      api.getTodaysGamesWithOverrides(next)
        .then((result) => { setData(result); setLastUpdated(new Date()); })
        .catch((err) => console.error("Override recalculation failed:", err));
      return next;
    });
  }, []);

  const handleCopyFullSlate = async () => {
    try {
      const result = await api.getAiPrompt();
      await copyToClipboard(result.prompt);
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    } catch {
      if (data) {
        const lines = data.games.map(
          (g) => `${g.away.team} @ ${g.home.team}: ${Object.entries(g.markets).map(([t, m]) => `${t} ${m.edge.best_side} ${(m.edge.best_edge * 100).toFixed(1)}%`).join(" | ")}`
        );
        await copyToClipboard(lines.join("\n"));
      }
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    }
  };

  /** Click a summary row or top edge → scroll to game card and expand it */
  const handleGameClick = useCallback((gameId: string) => {
    setExpandedGameId(gameId);
    // Small delay to let state propagate + GameCard re-render before scroll
    setTimeout(() => scrollToGame(gameId), 100);
  }, []);

  const lastUpdatedStr = lastUpdated
    ? lastUpdated.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true })
    : null;

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Loading spinner */}
        {loading && !data && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-10 h-10 border-2 border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin mb-4" />
            <p className="text-[#94a3b8] text-sm">Fetching live data from NBA API & Polymarket...</p>
            <p className="text-[#64748b] text-xs mt-1">First load may take up to 60s</p>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg p-4 mb-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-[#FF1744] font-medium">Connection Error</p>
              <p className="text-xs text-[#FF1744]/70 mt-0.5">{error}</p>
            </div>
            <button onClick={() => loadData()} className="px-3 py-1.5 text-xs rounded bg-[#FF1744]/20 text-[#FF1744] border border-[#FF1744]/30 hover:bg-[#FF1744]/30 transition-colors font-medium">
              Retry
            </button>
          </div>
        )}

        {data && (
          <>
            {/* Top Edges — clickable */}
            <TopEdges edges={data.top_edges} onEdgeClick={handleGameClick} />

            {/* ── Summary Table ── */}
            {data.games.length > 0 && (
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden mb-6">
                <div className="px-4 py-2.5 bg-[#1a2235] flex items-center justify-between">
                  <h2 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
                    Today&apos;s Slate ({data.games_count} games)
                  </h2>
                  <div className="flex items-center gap-2">
                    {lastUpdatedStr && (
                      <span className="text-[10px] text-[#64748b] font-mono">Updated {lastUpdatedStr}</span>
                    )}
                    {refreshing && (
                      <div className="w-3 h-3 border border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin" />
                    )}
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[10px] text-[#64748b] uppercase bg-[#0d1320]">
                        <th className="text-left py-2 px-4">Game</th>
                        <th className="text-left py-2 px-2">Time</th>
                        <th className="text-left py-2 px-2">Status</th>
                        <th className="text-right py-2 px-2">Win Prob</th>
                        <th className="text-right py-2 px-2">Spread</th>
                        <th className="text-right py-2 px-2">Total</th>
                        <th className="text-left py-2 px-2">Best Edge</th>
                        <th className="text-right py-2 px-3">Edge %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.games.map((g) => {
                        const fav = getFavored(g);
                        const bestMkt = getBestEdge(g);
                        const isLive = g.live?.game_status === 2;
                        const isFinal = g.live?.game_status === 3;

                        return (
                          <tr
                            key={g.game_id}
                            onClick={() => handleGameClick(g.game_id)}
                            className="border-t border-[#1e293b] hover:bg-[#1a2235] cursor-pointer transition-colors"
                          >
                            <td className="py-2.5 px-4 font-semibold text-[#e2e8f0] whitespace-nowrap">
                              {g.away.team} @ {g.home.team}
                            </td>
                            <td className="py-2.5 px-2 text-xs text-[#64748b] font-mono whitespace-nowrap">
                              {isLive ? (
                                <span className="text-[#FF1744]">Q{g.live.period} {g.live.game_clock}</span>
                              ) : isFinal ? (
                                <span className="text-[#64748b]">Final</span>
                              ) : (
                                formatSGT(g.tipoff_sgt)
                              )}
                            </td>
                            <td className="py-2.5 px-2">
                              {isLive && (
                                <span className="text-xs font-mono font-semibold text-[#FF1744]">
                                  {g.live.away_score}-{g.live.home_score}
                                </span>
                              )}
                              {isFinal && (
                                <span className="text-xs font-mono font-semibold text-[#94a3b8]">
                                  {g.live.away_score}-{g.live.home_score}
                                </span>
                              )}
                              {!isLive && !isFinal && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#2979FF]/10 text-[#2979FF] border border-[#2979FF]/20 font-medium">
                                  SCHED
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono text-[#e2e8f0] whitespace-nowrap">
                              {fav.name} {formatPct(fav.prob)}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono text-[#94a3b8] whitespace-nowrap">
                              {g.home.team} {g.model.projected_spread > 0 ? "+" : ""}{g.model.projected_spread.toFixed(1)}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono text-[#94a3b8]">
                              {g.model.projected_total.toFixed(1)}
                            </td>
                            <td className="py-2.5 px-2 whitespace-nowrap">
                              {bestMkt && !isFinal ? (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${getVerdictBg(bestMkt.edge.verdict)}`}>
                                  {bestMkt.edge.verdict}
                                </span>
                              ) : isFinal ? (
                                <span className="text-[10px] text-[#475569]">Resolved</span>
                              ) : (
                                <span className="text-[10px] text-[#475569]">—</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-semibold whitespace-nowrap">
                              {bestMkt && !isFinal ? (
                                <span className="text-[#4CAF50]">{formatEdge(bestMkt.edge.best_edge)}</span>
                              ) : (
                                <span className="text-[#475569]">—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="px-4 py-1.5 bg-[#0d1320] text-[10px] text-[#475569]">
                  Click any row to jump to full game details below
                </div>
              </div>
            )}

            {/* Controls bar */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
                Game Details
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="px-3 py-1.5 text-xs rounded bg-[#1a2235] text-[#94a3b8] border border-[#1e293b] hover:border-[#334155] hover:text-[#e2e8f0] transition-colors font-medium disabled:opacity-50"
                >
                  {refreshing ? "Refreshing..." : "↻ Refresh"}
                </button>
                <button
                  onClick={handleCopyFullSlate}
                  className="px-3 py-1.5 text-xs rounded bg-[#2979FF]/20 text-[#2979FF] border border-[#2979FF]/30 hover:bg-[#2979FF]/30 transition-colors font-medium"
                >
                  {aiPromptCopied ? "✓ Copied!" : "Copy Full Slate AI Prompt"}
                </button>
              </div>
            </div>

            {/* Data quality warnings */}
            {data.games.length > 0 && data.games[0].data_quality?.warnings?.length > 0 && (
              <div className="bg-[#FFD600]/10 border border-[#FFD600]/20 rounded-lg p-3 mb-4">
                <p className="text-xs font-semibold text-[#FFD600] mb-1">Data Warnings</p>
                {data.games[0].data_quality.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-[#FFD600]/80">• {w}</p>
                ))}
              </div>
            )}

            {/* Game Cards */}
            {data.games.length > 0 ? (
              <div className="space-y-4">
                {data.games.map((game) => (
                  <div key={game.game_id} id={`game-${game.game_id}`} className="transition-all duration-300 rounded-lg">
                    <GameCard
                      game={game}
                      injuryOverrides={injuryOverrides}
                      onInjuryToggle={handleInjuryToggle}
                      forceExpanded={expandedGameId === game.game_id}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState />
            )}
          </>
        )}
      </main>

      <footer className="border-t border-[#1e293b] mt-12 py-4 text-center text-xs text-[#64748b]">
        CourtEdge v0.1 — Lineup-adjusted NBA analytics for Polymarket
        {data && ` — ${data.date}`}
      </footer>
    </div>
  );
}
