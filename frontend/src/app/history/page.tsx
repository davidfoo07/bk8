"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import GameCard from "@/components/GameCard";
import type { DailyAnalysis } from "@/types/api";
import { api, type SavedDateEntry } from "@/lib/api";

export default function HistoryPage() {
  const [dates, setDates] = useState<SavedDateEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [data, setData] = useState<DailyAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingGames, setLoadingGames] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Dummy overrides state (history is read-only, no toggles)
  const [injuryOverrides] = useState<Record<string, string>>({});

  // Load saved dates on mount
  useEffect(() => {
    const loadDates = async () => {
      try {
        const result = await api.getHistoryDates();
        setDates(result);
        // Auto-select most recent date
        if (result.length > 0) {
          setSelectedDate(result[0].date);
        }
      } catch (e) {
        setError("Failed to load prediction history");
      } finally {
        setLoading(false);
      }
    };
    loadDates();
  }, []);

  // Load games when date changes
  useEffect(() => {
    if (!selectedDate) return;

    const loadGames = async () => {
      setLoadingGames(true);
      setError(null);
      try {
        const result = await api.getHistoryForDate(selectedDate);
        setData(result);
      } catch (e) {
        setError(`Failed to load predictions for ${selectedDate}`);
        setData(null);
      } finally {
        setLoadingGames(false);
      }
    };
    loadGames();
  }, [selectedDate]);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + "T12:00:00");
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatSavedAt = (savedAt: string | null) => {
    if (!savedAt) return "";
    const d = new Date(savedAt);
    return d.toLocaleString("en-US", {
      timeZone: "Asia/Singapore",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }) + " SGT";
  };

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-[#e2e8f0]">
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-[#e2e8f0]">Prediction History</h2>
            <p className="text-sm text-[#64748b] mt-1">
              Browse saved predictions — every pipeline run is auto-saved for reference
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2979FF]" />
          </div>
        ) : dates.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-lg text-[#94a3b8]">No saved predictions yet</p>
            <p className="text-sm text-[#64748b] mt-2">
              Predictions are auto-saved every time you load the dashboard.
              Go to the Dashboard first to generate today's predictions.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-[240px_1fr] gap-6">
            {/* Date sidebar */}
            <div className="space-y-1">
              <p className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">
                Saved Dates
              </p>
              {dates.map((entry) => (
                <button
                  key={entry.date}
                  onClick={() => setSelectedDate(entry.date)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                    selectedDate === entry.date
                      ? "bg-[#2979FF]/20 border border-[#2979FF]/40 text-[#e2e8f0]"
                      : "bg-[#111827] border border-[#1e293b] text-[#94a3b8] hover:border-[#334155]"
                  }`}
                >
                  <p className="text-sm font-semibold">{formatDate(entry.date)}</p>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-xs text-[#64748b]">
                      {entry.games_count} games
                    </span>
                    <span className="text-[10px] text-[#64748b]">
                      {formatSavedAt(entry.saved_at)}
                    </span>
                  </div>
                </button>
              ))}
            </div>

            {/* Game cards */}
            <div>
              {loadingGames ? (
                <div className="flex items-center justify-center py-20">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2979FF]" />
                </div>
              ) : error ? (
                <div className="text-center py-20">
                  <p className="text-lg text-[#FF1744]">{error}</p>
                </div>
              ) : data ? (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <h3 className="text-lg font-semibold text-[#e2e8f0]">
                      {formatDate(selectedDate!)}
                    </h3>
                    <span className="text-xs px-2 py-0.5 rounded bg-[#7C4DFF]/20 text-[#7C4DFF] font-mono">
                      {data.games_count} games
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-[#FFD600]/15 text-[#FFD600] border border-[#FFD600]/30">
                      SAVED
                    </span>
                  </div>

                  {/* Top Edges from saved data */}
                  {data.top_edges && data.top_edges.length > 0 && (
                    <div className="mb-4 p-3 bg-[#111827] border border-[#1e293b] rounded-lg">
                      <p className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-2">
                        Top Edges (at time of prediction)
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {data.top_edges.slice(0, 5).map((edge, i) => (
                          <span
                            key={i}
                            className={`text-xs px-2 py-1 rounded font-mono ${
                              edge.verdict === "STRONG BUY"
                                ? "bg-[#00C853]/15 text-[#00C853] border border-[#00C853]/30"
                                : "bg-[#4CAF50]/10 text-[#4CAF50] border border-[#4CAF50]/30"
                            }`}
                          >
                            {edge.selection} @ {Math.round(edge.price * 100)}¢ ({edge.edge > 0 ? "+" : ""}{(edge.edge * 100).toFixed(1)}%)
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-4">
                    {data.games.map((game) => (
                      <GameCard
                        key={game.game_id}
                        game={game}
                        injuryOverrides={injuryOverrides}
                        onInjuryToggle={() => {}} // Read-only in history
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
