"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import Header from "@/components/Header";
import TopEdges from "@/components/TopEdges";
import GameCard from "@/components/GameCard";
import EmptyState from "@/components/EmptyState";
import type { DailyAnalysis } from "@/types/api";
import { api } from "@/lib/api";
import { copyToClipboard } from "@/lib/utils";

const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 minutes

export default function Dashboard() {
  const [data, setData] = useState<DailyAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiPromptCopied, setAiPromptCopied] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Injury overrides: { "Victor Wembanyama": "FULL", "Stephon Castle": "OFF" }
  const [injuryOverrides, setInjuryOverrides] = useState<Record<string, string>>({});

  const loadData = useCallback(async (isRefresh = false, overrides?: Record<string, string>) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const effectiveOverrides = overrides ?? injuryOverrides;
      const hasOverrides = Object.keys(effectiveOverrides).length > 0;
      const result = hasOverrides
        ? await api.getTodaysGamesWithOverrides(effectiveOverrides)
        : await api.getTodaysGames();
      setData(result);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load data";
      setError(message);
      if (!isRefresh) {
        setData(null);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [injuryOverrides]);

  // Initial load + auto-refresh
  useEffect(() => {
    loadData();
    timerRef.current = setInterval(() => loadData(true), AUTO_REFRESH_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/games/refresh`,
        { method: "POST" }
      );
    } catch {
      // Ignore — we'll re-fetch anyway
    }
    // Clear overrides on hard refresh
    setInjuryOverrides({});
    await loadData(true, {});
  };

  /** Called from GameCard when user toggles a QUESTIONABLE player */
  const handleInjuryToggle = useCallback(
    (playerName: string, mode: "FULL" | "HALF" | "OFF") => {
      setInjuryOverrides((prev) => {
        const next = { ...prev };
        if (mode === "HALF") {
          // HALF is the default — remove override to restore default behavior
          delete next[playerName];
        } else {
          next[playerName] = mode;
        }
        // Immediately re-fetch with new overrides
        setTimeout(() => loadData(true, next), 0);
        return next;
      });
    },
    [loadData]
  );

  const handleCopyFullSlate = async () => {
    try {
      const result = await api.getAiPrompt();
      await copyToClipboard(result.prompt);
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    } catch {
      if (data) {
        const lines = data.games.map(
          (g) =>
            `${g.away.team} @ ${g.home.team}: ${Object.entries(g.markets)
              .map(
                ([t, m]) =>
                  `${t} ${m.edge.best_side} ${(m.edge.best_edge * 100).toFixed(1)}%`
              )
              .join(" | ")}`
        );
        await copyToClipboard(lines.join("\n"));
      }
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    }
  };

  const lastUpdatedStr = lastUpdated
    ? lastUpdated.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      })
    : null;

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Initial loading spinner */}
        {loading && !data && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-10 h-10 border-2 border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin mb-4" />
            <p className="text-[#94a3b8] text-sm">
              Fetching live data from NBA API & Polymarket...
            </p>
            <p className="text-[#64748b] text-xs mt-1">
              First load may take up to 60s
            </p>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg p-4 mb-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-[#FF1744] font-medium">Connection Error</p>
              <p className="text-xs text-[#FF1744]/70 mt-0.5">{error}</p>
            </div>
            <button
              onClick={() => loadData()}
              className="px-3 py-1.5 text-xs rounded bg-[#FF1744]/20 text-[#FF1744] border border-[#FF1744]/30 hover:bg-[#FF1744]/30 transition-colors font-medium"
            >
              Retry
            </button>
          </div>
        )}

        {/* Main content */}
        {data && (
          <>
            <TopEdges edges={data.top_edges} />

            {/* Controls bar */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
                  Games ({data.games_count})
                </h2>
                {lastUpdatedStr && (
                  <span className="text-xs text-[#64748b] font-mono">
                    Updated {lastUpdatedStr}
                  </span>
                )}
                {refreshing && (
                  <div className="w-3 h-3 border border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin" />
                )}
              </div>
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
                  <GameCard
                    key={game.game_id}
                    game={game}
                    injuryOverrides={injuryOverrides}
                    onInjuryToggle={handleInjuryToggle}
                  />
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
