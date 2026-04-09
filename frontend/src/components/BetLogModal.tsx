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

/** Determine which YES/NO side the model recommends for this market */
function getSystemSide(m: MarketEdge): "YES" | "NO" {
  if (m.home_label) return m.edge.best_side === m.home_label ? "YES" : "NO";
  return m.edge.best_side === "YES" ? "YES" : "NO";
}

/** Build button labels: YES = home/Over, NO = away/Under */
function getSideLabels(
  type: string,
  m: MarketEdge,
  game: GameAnalysis,
): { yesLabel: string; noLabel: string } {
  if (type === "moneyline" || type === "ml") {
    return {
      yesLabel: `${game.home.team} ML`,
      noLabel: `${game.away.team} ML`,
    };
  }
  if (type === "spread" && m.line != null) {
    const homeLine = m.line >= 0 ? `+${m.line}` : `${m.line}`;
    const awayLine = -m.line >= 0 ? `+${-m.line}` : `${-m.line}`;
    return {
      yesLabel: `${game.home.team} ${homeLine}`,
      noLabel: `${game.away.team} ${awayLine}`,
    };
  }
  if (type === "total" && m.line != null) {
    return {
      yesLabel: `Over ${m.line}`,
      noLabel: `Under ${m.line}`,
    };
  }
  return {
    yesLabel: m.home_label || "YES",
    noLabel: m.away_label || "NO",
  };
}

/** Compute derived values for the user's chosen side */
function computeSideValues(m: MarketEdge, side: "YES" | "NO") {
  const price =
    side === "YES"
      ? (m.polymarket_home_yes || 0)
      : (m.polymarket_home_no || 0);
  const modelProb =
    side === "YES" ? m.model_probability : 1 - m.model_probability;
  const edge = side === "YES" ? m.edge.yes_edge : m.edge.no_edge;
  // Quarter-Kelly for chosen side
  const kellyFull =
    price > 0 && price < 1
      ? Math.max(0, (modelProb - price) / (1 - price))
      : 0;
  const kellyQuarter = kellyFull * 0.25;
  return { price, modelProb, edge, kellyQuarter };
}

/** Map edge magnitude to a verdict label */
function edgeToVerdict(edge: number): string {
  if (edge >= 0.06) return "STRONG BUY";
  if (edge >= 0.03) return "BUY";
  if (edge >= 0.01) return "LEAN";
  return "NO EDGE";
}

export default function BetLogModal({
  game,
  onClose,
  onBetPlaced,
}: BetLogModalProps) {
  const marketEntries = Object.entries(game.markets);

  // Pre-select market with the highest edge
  const bestEntry = marketEntries.reduce(
    (best, [type]) =>
      game.markets[type].edge.best_edge >
      (best ? game.markets[best].edge.best_edge : 0)
        ? type
        : best,
    marketEntries[0]?.[0] || "",
  );

  const [selectedMarket, setSelectedMarket] = useState(bestEntry);

  // Track chosen YES/NO side per market; default = system recommendation
  const [chosenSides, setChosenSides] = useState<Record<string, "YES" | "NO">>(
    () => {
      const sides: Record<string, "YES" | "NO"> = {};
      for (const [type, m] of Object.entries(game.markets)) {
        sides[type] = getSystemSide(m);
      }
      return sides;
    },
  );

  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const market = game.markets[selectedMarket];
  if (!market) return null;

  // Derive all computed values
  const systemSide = getSystemSide(market);
  const chosenSide = chosenSides[selectedMarket] || systemSide;
  const isSystemAligned = chosenSide === systemSide;
  const labels = getSideLabels(selectedMarket, market, game);
  const { price, modelProb, edge, kellyQuarter } = computeSideValues(
    market,
    chosenSide,
  );
  const chosenVerdict = edgeToVerdict(edge);
  const parsedAmount = parseFloat(amount) || 0;

  const pickSide = (side: "YES" | "NO") => {
    setChosenSides((prev) => ({ ...prev, [selectedMarket]: side }));
  };

  const handleSubmit = async () => {
    if (parsedAmount <= 0) {
      setError("Enter a valid bet amount");
      return;
    }

    setSubmitting(true);
    setError(null);

    const selectionLabel =
      chosenSide === "YES" ? labels.yesLabel : labels.noLabel;

    const bet: BetCreate = {
      game_id: game.game_id,
      market_type: selectedMarket,
      selection: `${game.away.team} @ ${game.home.team} — ${selectionLabel}`,
      side: chosenSide,
      entry_price: price,
      model_probability: modelProb,
      edge_at_entry: edge,
      amount_usd: parsedAmount,
      kelly_fraction: kellyQuarter,
      notes,
      system_aligned: isSystemAligned,
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

  /** Style for a side-picker button based on selection state + alignment */
  const sideButtonClass = (side: "YES" | "NO") => {
    const isChosen = chosenSide === side;
    if (!isChosen) {
      return "border-[#1e293b] bg-[#0d1320] text-[#94a3b8] hover:border-[#334155]";
    }
    // Chosen side — blue if aligned with system, amber if against
    return isSystemAligned
      ? "border-[#2979FF] bg-[#2979FF]/15 text-[#2979FF]"
      : "border-[#FFD600] bg-[#FFD600]/15 text-[#FFD600]";
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
          {/* Market selector tabs */}
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
                  <span
                    className={`block text-xs mt-0.5 ${getVerdictColor(m.edge.verdict)}`}
                  >
                    {formatEdge(m.edge.best_edge)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Side picker — YES (home/Over) vs NO (away/Under) */}
          <div>
            <label className="text-xs text-[#64748b] uppercase tracking-wider font-semibold mb-1 block">
              Pick Side
            </label>
            <div className="flex gap-2">
              {/* YES (home-perspective) button */}
              <button
                onClick={() => pickSide("YES")}
                className={`flex-1 px-3 py-2.5 rounded-md text-sm font-semibold border-2 transition-all ${sideButtonClass("YES")}`}
              >
                {labels.yesLabel}
                {systemSide === "YES" && (
                  <span className="block text-[10px] mt-0.5 text-[#4CAF50] font-medium">
                    System Pick
                  </span>
                )}
              </button>

              {/* NO (away-perspective) button */}
              <button
                onClick={() => pickSide("NO")}
                className={`flex-1 px-3 py-2.5 rounded-md text-sm font-semibold border-2 transition-all ${sideButtonClass("NO")}`}
              >
                {labels.noLabel}
                {systemSide === "NO" && (
                  <span className="block text-[10px] mt-0.5 text-[#4CAF50] font-medium">
                    System Pick
                  </span>
                )}
              </button>
            </div>

            {/* Alignment badge */}
            <div className="mt-2 flex justify-center">
              {isSystemAligned ? (
                <span className="text-xs px-2.5 py-1 rounded-full bg-[#4CAF50]/15 text-[#4CAF50] border border-[#4CAF50]/30 font-semibold">
                  System Pick ✓
                </span>
              ) : (
                <span className="text-xs px-2.5 py-1 rounded-full bg-[#FFD600]/15 text-[#FFD600] border border-[#FFD600]/30 font-semibold">
                  Against System
                </span>
              )}
            </div>
          </div>

          {/* Edge info for chosen side */}
          <div className="bg-[#0d1320] rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Selection</span>
              <span className="text-sm font-semibold text-[#e2e8f0]">
                {chosenSide === "YES" ? labels.yesLabel : labels.noLabel}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Polymarket Price</span>
              <span className="text-sm font-mono text-[#e2e8f0]">
                {formatPrice(price)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Model Probability</span>
              <span className="text-sm font-mono text-[#e2e8f0]">
                {formatPct(modelProb)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Edge</span>
              <span
                className={`text-sm font-mono font-semibold ${
                  edge > 0
                    ? "text-[#4CAF50]"
                    : edge < 0
                      ? "text-[#FF1744]"
                      : "text-[#78909C]"
                }`}
              >
                {formatEdge(edge)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Verdict</span>
              <span
                className={`text-xs px-2 py-0.5 rounded border font-semibold ${getVerdictBg(chosenVerdict)}`}
              >
                {chosenVerdict}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#64748b]">Quarter-Kelly</span>
              <span className="text-sm font-mono text-[#94a3b8]">
                {(kellyQuarter * 100).toFixed(1)}% of bankroll
              </span>
            </div>
          </div>

          {/* Amount input */}
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

          {/* Notes input */}
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
            className={`px-4 py-2 text-sm rounded-md font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              isSystemAligned
                ? "bg-[#2979FF] text-white hover:bg-[#2979FF]/80"
                : "bg-[#FFD600] text-[#0a0e17] hover:bg-[#FFD600]/80"
            }`}
          >
            {submitting ? "Logging..." : success ? "✓ Logged" : "Log Bet"}
          </button>
        </div>
      </div>
    </div>
  );
}
