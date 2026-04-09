"use client";

import { useState } from "react";
import type { GameAnalysis, MarketEdge, BetCreate } from "@/types/api";
import { api } from "@/lib/api";
import {
  formatPct,
  formatPrice,
  formatEdge,
  getVerdictBg,
  getVerdictColor,
} from "@/lib/utils";

interface BetLogModalProps {
  game: GameAnalysis;
  onClose: () => void;
  onBetPlaced: () => void;
}

/** Get the Polymarket price for the recommended side */
function getPickPrice(m: MarketEdge): number {
  const isHome =
    m.home_label
      ? m.edge.best_side === m.home_label
      : m.edge.best_side === "YES";
  return isHome ? (m.polymarket_home_yes || 0) : (m.polymarket_home_no || 0);
}

/** Get the model probability for the recommended side */
function getPickProb(m: MarketEdge): number {
  const isHome =
    m.home_label
      ? m.edge.best_side === m.home_label
      : m.edge.best_side === "YES";
  return isHome ? m.model_probability : 1 - m.model_probability;
}

/** Build a selection label */
function buildSelection(m: MarketEdge, type: string): string {
  const side = m.edge.best_side;
  if (type === "spread" && m.line != null) {
    const isHome = side === m.home_label;
    const line = isHome ? m.line : -m.line;
    const lineStr = line > 0 ? `+${line}` : `${line}`;
    return `${side} ${lineStr}`;
  }
  if (type === "total" && m.line != null) {
    return `${side} ${m.line}`;
  }
  return `${side} ML`;
}

export default function BetLogModal({ game, onClose, onBetPlaced }: BetLogModalProps) {
  // Pre-select the market with the best edge
  const marketEntries = Object.entries(game.markets);
  const bestEntry = marketEntries.reduce(
    (best, [type, m]) =>
      m.edge.best_edge > (best ? game.markets[best].edge.best_edge : 0)
        ? type
        : best,
    marketEntries[0]?.[0] || ""
  );

  const [selectedMarket, setSelectedMarket] = useState(bestEntry);
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const market = game.markets[selectedMarket];
  if (!market) return null;

  const pickPrice = getPickPrice(market);
  const pickProb = getPickProb(market);
  const selection = buildSelection(market, selectedMarket);
  const side = market.home_label
    ? (market.edge.best_side === market.home_label ? "YES" : "NO")
    : market.edge.best_side;

  // Calculate Kelly-recommended amount based on bankroll input
  const parsedAmount = parseFloat(amount) || 0;

  const handleSubmit = async () => {
    if (parsedAmount <= 0) {
      setError("Enter a valid bet amount");
      return;
    }

    setSubmitting(true);
    setError(null);

    const bet: BetCreate = {
      game_id: game.game_id,
      market_type: selectedMarket,
      selection: `${game.away.team} @ ${game.home.team} — ${selection}`,
      side: side,
      entry_price: pickPrice,
      model_probability: pickProb,
      edge_at_entry: market.edge.best_edge,
      amount_usd: parsedAmount,
      kelly_fraction: market.edge.kelly_fraction,
      notes: notes,
    };

    try {
      await api.createBet(bet);
      setSuccess(true);
      setTimeout(() => {
        onBetPlaced();
        onClose();
      }, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log bet");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-[#111827] border border-[#1e293b] rounded-xl w-full max-w-lg mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#1e293b]">
          <h2 className="text-lg font-semibold text-[#e2e8f0]">
            Log Bet — {game.away.team} @ {game.home.team}
          </h2>
          <button
            onClick={onClose}
            className="text-[#64748b] hover:text-[#e2e8f0] transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {/* Market selector */}
          <div>
            <label className="text-xs text-[#64748b] uppercase tracking-wider font-semibold mb-1 block">
              Market
            </label>
            <div className="flex gap-2">
              {marketEntries.map(([type, m]) => (
                <button
                  key={type}
                  onClick={() => setSelectedMarket(type)}
                  className={`flex-1 px-3 py-2 rounded-md text-sm font-medium border transition-all ${
                    selectedMarket === type
                      ? "border-[#2979FF] bg-[#2979FF]/15 text-[#2979FF]"
                      : "border-[#1e293b] bg-[#0d1320] text-[#94a3b8] hover:border-[#334155]"
                  }`}
                >
                  <span className="capitalize">{type}</span>
                  <span className={`block text-xs mt-0.5 ${getVerdictColor(m.edge.verdict)}`}>
                    {formatEdge(m.edge.best_edge)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Pre-filled edge info */}
          <div className="bg-[#0d1320] rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Selection</span>
              <span className="text-sm font-semibold text-[#e2e8f0]">{selection}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Polymarket Price</span>
              <span className="text-sm font-mono text-[#e2e8f0]">{formatPrice(pickPrice)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Model Probability</span>
              <span className="text-sm font-mono text-[#e2e8f0]">{formatPct(pickProb)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Edge</span>
              <span className={`text-sm font-mono font-semibold ${getVerdictColor(market.edge.verdict)}`}>
                {formatEdge(market.edge.best_edge)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Verdict</span>
              <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${getVerdictBg(market.edge.verdict)}`}>
                {market.edge.verdict}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Quarter-Kelly</span>
              <span className="text-sm font-mono text-[#94a3b8]">
                {market.edge.suggested_bet_pct.toFixed(1)}% of bankroll
              </span>
            </div>
          </div>

          {/* User inputs */}
          <div>
            <label className="text-xs text-[#64748b] uppercase tracking-wider font-semibold mb-1 block">
              Amount (USD)
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="50.00"
              min="1"
              step="1"
              className="w-full px-3 py-2 rounded-md bg-[#0d1320] border border-[#1e293b] text-[#e2e8f0] font-mono text-sm focus:border-[#2979FF] focus:outline-none placeholder:text-[#475569]"
            />
          </div>

          <div>
            <label className="text-xs text-[#64748b] uppercase tracking-wider font-semibold mb-1 block">
              Notes (optional)
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Mobley resting for CLE, MEM also missing Bane"
              className="w-full px-3 py-2 rounded-md bg-[#0d1320] border border-[#1e293b] text-[#e2e8f0] text-sm focus:border-[#2979FF] focus:outline-none placeholder:text-[#475569]"
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-sm text-[#FF1744] bg-[#FF1744]/10 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {/* Success */}
          {success && (
            <p className="text-sm text-[#00C853] bg-[#00C853]/10 px-3 py-2 rounded font-semibold">
              ✓ Bet logged successfully!
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-[#1e293b]">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-md bg-[#1a2235] text-[#94a3b8] border border-[#1e293b] hover:border-[#334155] transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || success || parsedAmount <= 0}
            className="px-4 py-2 text-sm rounded-md bg-[#2979FF] text-white font-semibold hover:bg-[#2979FF]/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Logging..." : success ? "✓ Logged" : "Log Bet"}
          </button>
        </div>
      </div>
    </div>
  );
}
