"use client";

import { useEffect, useState } from "react";
import Header from "@/components/Header";
import type { BetHistoryResponse } from "@/types/api";
import { formatPct, formatEdge, getVerdictColor } from "@/lib/utils";

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

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        <h1 className="text-xl font-bold text-[#e2e8f0] mb-6">Bet Tracker</h1>

        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
            <span className="text-xs text-[#64748b] uppercase">Total Bets</span>
            <p className="text-2xl font-mono font-bold text-[#e2e8f0] mt-1">{history.total_bets}</p>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
            <span className="text-xs text-[#64748b] uppercase">Win Rate</span>
            <p className="text-2xl font-mono font-bold text-[#4CAF50] mt-1">
              {history.total_bets > 0 ? formatPct(history.win_rate) : "—"}
            </p>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
            <span className="text-xs text-[#64748b] uppercase">Total P&L</span>
            <p className={`text-2xl font-mono font-bold mt-1 ${history.total_pnl >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"}`}>
              ${history.total_pnl.toFixed(2)}
            </p>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4">
            <span className="text-xs text-[#64748b] uppercase">ROI</span>
            <p className={`text-2xl font-mono font-bold mt-1 ${history.roi >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"}`}>
              {history.roi.toFixed(1)}%
            </p>
          </div>
        </div>

        {/* Bet History Table */}
        {history.bets.length > 0 ? (
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-[#64748b] uppercase border-b border-[#1e293b]">
                  <th className="text-left p-3">Game</th>
                  <th className="text-left p-3">Selection</th>
                  <th className="text-right p-3">Price</th>
                  <th className="text-right p-3">Edge</th>
                  <th className="text-right p-3">Amount</th>
                  <th className="text-center p-3">Result</th>
                  <th className="text-right p-3">P&L</th>
                </tr>
              </thead>
              <tbody>
                {history.bets.map((bet) => (
                  <tr key={bet.id} className="border-t border-[#1e293b]">
                    <td className="p-3 font-mono text-[#e2e8f0]">{bet.game_id}</td>
                    <td className="p-3 text-[#e2e8f0]">{bet.selection}</td>
                    <td className="p-3 text-right font-mono text-[#e2e8f0]">
                      {(bet.entry_price * 100).toFixed(0)}¢
                    </td>
                    <td className="p-3 text-right font-mono text-[#4CAF50]">
                      {formatEdge(bet.edge_at_entry)}
                    </td>
                    <td className="p-3 text-right font-mono text-[#e2e8f0]">
                      ${bet.amount_usd.toFixed(2)}
                    </td>
                    <td className="p-3 text-center">
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-semibold ${
                          bet.result === "WIN"
                            ? "bg-[#4CAF50]/20 text-[#4CAF50]"
                            : bet.result === "LOSS"
                            ? "bg-[#FF1744]/20 text-[#FF1744]"
                            : "bg-[#78909C]/20 text-[#78909C]"
                        }`}
                      >
                        {bet.result || "PENDING"}
                      </span>
                    </td>
                    <td className={`p-3 text-right font-mono ${(bet.pnl || 0) >= 0 ? "text-[#4CAF50]" : "text-[#FF1744]"}`}>
                      {bet.pnl !== null ? `$${bet.pnl.toFixed(2)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12 text-[#94a3b8]">
            <p className="text-lg mb-2">No bets recorded yet</p>
            <p className="text-sm text-[#64748b]">
              Log your first bet from the dashboard to start tracking performance.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
