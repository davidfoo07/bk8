"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import type { BetHistoryResponse } from "@/types/api";
import { api } from "@/lib/api";
import { formatPct, formatEdge } from "@/lib/utils";

export default function BetTracker() {
  const [history, setHistory] = useState<BetHistoryResponse>({
    total_bets: 0,
    wins: 0,
    losses: 0,
    pushes: 0,
    pending: 0,
    total_pnl: 0,
    win_rate: 0,
    roi: 0,
    bets: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.getBetHistory();
      setHistory(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load bet history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-[#e2e8f0]">Bet Tracker</h1>
          <button
            onClick={loadHistory}
            className="px-3 py-1.5 text-xs rounded bg-[#1a2235] text-[#94a3b8] border border-[#1e293b] hover:border-[#334155] hover:text-[#e2e8f0] transition-colors font-medium"
          >
            ↻ Refresh
          </button>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-2 border-[#2979FF]/30 border-t-[#2979FF] rounded-full animate-spin" />
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg p-4 mb-6">
            <p className="text-sm text-[#FF1744]">{error}</p>
            <button
              onClick={loadHistory}
              className="mt-2 text-xs text-[#FF1744] underline hover:text-[#FF1744]/80"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && (
          <>
            {/* Stats Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
                <span className="text-xs text-[#64748b] uppercase">Total Bets</span>
                <p className="text-2xl font-mono font-bold text-[#e2e8f0] mt-1">{history.total_bets}</p>
                <p className="text-xs text-[#64748b] mt-0.5">
                  {history.pending > 0 ? `${history.pending} pending` : "—"}
                </p>
              </div>
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
                <span className="text-xs text-[#64748b] uppercase">Record (W-L-P)</span>
                <p className="text-2xl font-mono font-bold text-[#e2e8f0] mt-1">
                  {history.wins}-{history.losses}-{history.pushes}
                </p>
                <p className="text-xs text-[#64748b] mt-0.5">
                  {history.total_bets > 0 ? `Win rate: ${formatPct(history.win_rate)}` : "—"}
                </p>
              </div>
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
                <span className="text-xs text-[#64748b] uppercase">Total P&L</span>
                <p className={`text-2xl font-mono font-bold mt-1 ${history.total_pnl >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"}`}>
                  {history.total_pnl >= 0 ? "+" : ""}${history.total_pnl.toFixed(2)}
                </p>
              </div>
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
                <span className="text-xs text-[#64748b] uppercase">ROI</span>
                <p className={`text-2xl font-mono font-bold mt-1 ${history.roi >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"}`}>
                  {history.roi >= 0 ? "+" : ""}{history.roi.toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Bet History Table */}
            {history.bets.length > 0 ? (
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e293b]">
                  <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
                    Bet History ({history.bets.length})
                  </h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-[#64748b] uppercase border-b border-[#1e293b]">
                        <th className="text-left p-3">Date</th>
                        <th className="text-left p-3">Selection</th>
                        <th className="text-left p-3">Market</th>
                        <th className="text-right p-3">Price</th>
                        <th className="text-right p-3">Model</th>
                        <th className="text-right p-3">Edge</th>
                        <th className="text-right p-3">Amount</th>
                        <th className="text-right p-3">Kelly</th>
                        <th className="text-center p-3">Result</th>
                        <th className="text-right p-3">P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.bets.map((bet) => (
                        <tr key={bet.id} className="border-t border-[#1e293b] hover:bg-[#1a2235]/50">
                          <td className="p-3 text-xs font-mono text-[#94a3b8]">
                            {new Date(bet.placed_at).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                            })}
                          </td>
                          <td className="p-3 text-[#e2e8f0] max-w-[200px] truncate" title={bet.selection}>
                            {bet.selection}
                          </td>
                          <td className="p-3 text-[#94a3b8] capitalize">{bet.market_type}</td>
                          <td className="p-3 text-right font-mono text-[#e2e8f0]">
                            {(bet.entry_price * 100).toFixed(0)}¢
                          </td>
                          <td className="p-3 text-right font-mono text-[#94a3b8]">
                            {formatPct(bet.model_probability)}
                          </td>
                          <td className="p-3 text-right font-mono text-[#4CAF50]">
                            {formatEdge(bet.edge_at_entry)}
                          </td>
                          <td className="p-3 text-right font-mono text-[#e2e8f0]">
                            ${bet.amount_usd.toFixed(2)}
                          </td>
                          <td className="p-3 text-right font-mono text-[#94a3b8]">
                            {(bet.kelly_fraction * 100).toFixed(1)}%
                          </td>
                          <td className="p-3 text-center">
                            <span
                              className={`text-xs px-2 py-0.5 rounded font-semibold ${
                                bet.result === "WIN"
                                  ? "bg-[#4CAF50]/20 text-[#4CAF50]"
                                  : bet.result === "LOSS"
                                  ? "bg-[#FF1744]/20 text-[#FF1744]"
                                  : bet.result === "PUSH"
                                  ? "bg-[#FFD600]/20 text-[#FFD600]"
                                  : "bg-[#78909C]/20 text-[#78909C]"
                              }`}
                            >
                              {bet.result || "PENDING"}
                            </span>
                          </td>
                          <td className={`p-3 text-right font-mono font-semibold ${
                            (bet.pnl || 0) > 0 ? "text-[#4CAF50]" : (bet.pnl || 0) < 0 ? "text-[#FF1744]" : "text-[#78909C]"
                          }`}>
                            {bet.pnl !== null && bet.pnl !== undefined ? `${bet.pnl >= 0 ? "+" : ""}$${bet.pnl.toFixed(2)}` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-[#94a3b8]">
                <p className="text-4xl mb-4">📊</p>
                <p className="text-lg mb-2">No bets recorded yet</p>
                <p className="text-sm text-[#64748b]">
                  Log your first bet from the dashboard using the &quot;Log Bet&quot; button on any game card.
                </p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
