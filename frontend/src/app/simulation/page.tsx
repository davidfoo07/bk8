"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import { api } from "@/lib/api";
import type { SavedDateEntry, DailySimulation, SimBet } from "@/lib/api";

function formatPct(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatEdge(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}

type ViewMode = "flat" | "kelly";

export default function SimulationPage() {
  const [dates, setDates] = useState<SavedDateEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [simulation, setSimulation] = useState<DailySimulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [simLoading, setSimLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("flat");

  // Load available dates on mount
  const loadDates = useCallback(async () => {
    try {
      const data = await api.getSimulationDates();
      setDates(data);
      if (data.length > 0 && !selectedDate) {
        setSelectedDate(data[0].date);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dates");
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  // Load simulation when date changes
  const loadSimulation = useCallback(async (date: string) => {
    if (!date) return;
    setSimLoading(true);
    setError(null);
    try {
      const data = await api.getSimulation(date);
      setSimulation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load simulation");
      setSimulation(null);
    } finally {
      setSimLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDates();
  }, [loadDates]);

  useEffect(() => {
    if (selectedDate) {
      loadSimulation(selectedDate);
    }
  }, [selectedDate, loadSimulation]);

  // Get the result/pnl for current view mode
  const getResult = (bet: SimBet) =>
    viewMode === "flat" ? bet.flat_result : bet.kelly_result;
  const getPnl = (bet: SimBet) =>
    viewMode === "flat" ? bet.flat_pnl : bet.kelly_pnl;
  const getAmount = (bet: SimBet) =>
    viewMode === "flat" ? 1.0 : bet.kelly_amount;

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-[#e2e8f0]">System Simulation</h1>
            <p className="text-xs text-[#64748b] mt-0.5">
              What if you followed every model BUY/STRONG BUY at 100%?
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Date selector */}
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-[#111827] border border-[#1e293b] text-[#e2e8f0] text-sm rounded px-3 py-1.5 focus:outline-none focus:border-[#2979FF]"
            >
              {dates.map((d) => (
                <option key={d.date} value={d.date}>
                  {d.date} ({d.games_count} games)
                </option>
              ))}
            </select>
            {(loading || simLoading) && (
              <div className="w-5 h-5 border-2 border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin" />
            )}
          </div>
        </div>

        {error && (
          <div className="bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg p-4 mb-6">
            <p className="text-sm text-[#FF1744]">{error}</p>
          </div>
        )}

        {simulation && (
          <>
            {/* Stat Cards — Two rows: Flat and Kelly */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
              {/* Flat $1 Bets Card */}
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xs px-2 py-0.5 rounded bg-[#2979FF]/20 text-[#2979FF] font-semibold uppercase tracking-wider">
                    Flat $1 Bets
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">Record</span>
                    <p className="text-2xl font-mono font-bold text-[#e2e8f0] mt-1">
                      {simulation.flat_record}
                    </p>
                    <p className="text-xs text-[#64748b] mt-0.5">
                      {simulation.flat_wins + simulation.flat_losses > 0
                        ? `${((simulation.flat_wins / (simulation.flat_wins + simulation.flat_losses)) * 100).toFixed(0)}% win rate`
                        : "No graded bets"}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">P&L</span>
                    <p
                      className={`text-2xl font-mono font-bold mt-1 ${
                        simulation.flat_pnl >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"
                      }`}
                    >
                      {simulation.flat_pnl >= 0 ? "+" : ""}${simulation.flat_pnl.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">ROI</span>
                    <p
                      className={`text-2xl font-mono font-bold mt-1 ${
                        simulation.flat_roi >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"
                      }`}
                    >
                      {simulation.flat_roi >= 0 ? "+" : ""}{simulation.flat_roi.toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>

              {/* Kelly-Sized Card */}
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-5">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xs px-2 py-0.5 rounded bg-[#4CAF50]/20 text-[#4CAF50] font-semibold uppercase tracking-wider">
                    Kelly-Sized ($100 Bankroll)
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">Record</span>
                    <p className="text-2xl font-mono font-bold text-[#e2e8f0] mt-1">
                      {simulation.kelly_wins}/{simulation.kelly_wins + simulation.kelly_losses}
                    </p>
                    <p className="text-xs text-[#64748b] mt-0.5">
                      {simulation.kelly_wins + simulation.kelly_losses > 0
                        ? `${((simulation.kelly_wins / (simulation.kelly_wins + simulation.kelly_losses)) * 100).toFixed(0)}% win rate`
                        : "No graded bets"}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">P&L</span>
                    <p
                      className={`text-2xl font-mono font-bold mt-1 ${
                        simulation.kelly_pnl >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"
                      }`}
                    >
                      {simulation.kelly_pnl >= 0 ? "+" : ""}${simulation.kelly_pnl.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-[#64748b] uppercase">ROI</span>
                    <p
                      className={`text-2xl font-mono font-bold mt-1 ${
                        simulation.kelly_roi >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"
                      }`}
                    >
                      {simulation.kelly_roi >= 0 ? "+" : ""}{simulation.kelly_roi.toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Toggle + Bet Table */}
            {simulation.bets.length > 0 ? (
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e293b] flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
                    Virtual Bets ({simulation.total_bets})
                  </h2>
                  {/* Flat / Kelly toggle */}
                  <div className="flex bg-[#0a0e17] rounded p-0.5">
                    <button
                      onClick={() => setViewMode("flat")}
                      className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
                        viewMode === "flat"
                          ? "bg-[#2979FF] text-white"
                          : "text-[#94a3b8] hover:text-[#e2e8f0]"
                      }`}
                    >
                      Flat $1
                    </button>
                    <button
                      onClick={() => setViewMode("kelly")}
                      className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
                        viewMode === "kelly"
                          ? "bg-[#4CAF50] text-white"
                          : "text-[#94a3b8] hover:text-[#e2e8f0]"
                      }`}
                    >
                      Kelly
                    </button>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-[#64748b] uppercase border-b border-[#1e293b]">
                        <th className="text-left p-3">Game</th>
                        <th className="text-left p-3">Market</th>
                        <th className="text-left p-3">Your Bet</th>
                        <th className="text-center p-3">Verdict</th>
                        <th className="text-right p-3">Price</th>
                        <th className="text-right p-3">Model</th>
                        <th className="text-right p-3">Edge</th>
                        <th className="text-right p-3">Amount</th>
                        <th className="text-center p-3">Result</th>
                        <th className="text-right p-3">P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulation.bets.map((bet, i) => {
                        const result = getResult(bet);
                        const pnl = getPnl(bet);
                        const amount = getAmount(bet);

                        return (
                          <tr
                            key={`${bet.game}-${bet.market_type}-${i}`}
                            className="border-t border-[#1e293b] hover:bg-[#1a2235]/50"
                          >
                            <td className="p-3 text-[#94a3b8] font-semibold whitespace-nowrap">
                              {bet.game}
                            </td>
                            <td className="p-3 text-[#94a3b8] capitalize">{bet.market_type}</td>
                            <td className="p-3 text-[#e2e8f0] font-semibold whitespace-nowrap">
                              {bet.selection}
                            </td>
                            <td className="p-3 text-center">
                              <span
                                className={`text-xs px-2 py-0.5 rounded font-semibold border ${
                                  bet.verdict === "STRONG BUY"
                                    ? "bg-[#00C853]/20 text-[#00C853] border-[#00C853]/30"
                                    : "bg-[#4CAF50]/20 text-[#4CAF50] border-[#4CAF50]/30"
                                }`}
                              >
                                {bet.verdict}
                              </span>
                            </td>
                            <td className="p-3 text-right font-mono text-[#e2e8f0]">
                              {(bet.entry_price * 100).toFixed(0)}¢
                            </td>
                            <td className="p-3 text-right font-mono text-[#94a3b8]">
                              {formatPct(bet.model_prob)}
                            </td>
                            <td className="p-3 text-right font-mono text-[#4CAF50]">
                              {formatEdge(bet.edge)}
                            </td>
                            <td className="p-3 text-right font-mono text-[#e2e8f0]">
                              ${amount.toFixed(2)}
                            </td>
                            <td className="p-3 text-center">
                              <span
                                className={`text-xs px-2 py-0.5 rounded font-semibold ${
                                  result === "WIN"
                                    ? "bg-[#4CAF50]/20 text-[#4CAF50]"
                                    : result === "LOSS"
                                      ? "bg-[#FF1744]/20 text-[#FF1744]"
                                      : "bg-[#78909C]/20 text-[#78909C]"
                                }`}
                              >
                                {result || "PENDING"}
                              </span>
                            </td>
                            <td
                              className={`p-3 text-right font-mono font-semibold ${
                                pnl > 0
                                  ? "text-[#4CAF50]"
                                  : pnl < 0
                                    ? "text-[#FF1744]"
                                    : "text-[#78909C]"
                              }`}
                            >
                              {result
                                ? `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`
                                : "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-[#94a3b8]">
                <p className="text-4xl mb-4">🎰</p>
                <p className="text-lg mb-2">No qualifying bets found</p>
                <p className="text-sm text-[#64748b]">
                  No BUY or STRONG BUY verdicts in the saved predictions for this date.
                </p>
              </div>
            )}
          </>
        )}

        {!loading && !simLoading && dates.length === 0 && (
          <div className="text-center py-12 text-[#94a3b8]">
            <p className="text-4xl mb-4">📊</p>
            <p className="text-lg mb-2">No saved predictions yet</p>
            <p className="text-sm text-[#64748b]">
              Run the model from the Dashboard first to generate predictions that can be simulated.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
