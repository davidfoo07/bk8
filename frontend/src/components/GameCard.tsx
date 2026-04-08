"use client";

import { useState } from "react";
import type { GameAnalysis, InjuryInfo } from "@/types/api";
import {
  getVerdictBg,
  getVerdictColor,
  getDeltaIndicator,
  getDeltaColor,
  formatPct,
  formatPrice,
  formatEdge,
  formatET,
  formatSGT,
  copyToClipboard,
} from "@/lib/utils";

interface GameCardProps {
  game: GameAnalysis;
  injuryOverrides: Record<string, string>;
  onInjuryToggle: (playerName: string, mode: "FULL" | "HALF" | "OFF") => void;
}

/** Is the recommended side the "home" side of the market? */
function isHomeSide(m: GameAnalysis["markets"][string]): boolean {
  if (m.home_label) return m.edge.best_side === m.home_label;
  return m.edge.best_side === "YES";
}

/** Get the price for the recommended side */
function getBestPrice(m: GameAnalysis["markets"][string]): number {
  return isHomeSide(m) ? (m.polymarket_home_yes || 0) : (m.polymarket_home_no || 0);
}

/** Get the EV for the recommended side */
function getBestEv(m: GameAnalysis["markets"][string]): number {
  return isHomeSide(m) ? m.edge.yes_ev : m.edge.no_ev;
}

/** Format a line value with sign */
function formatLine(line: number | null | undefined, type: string): string {
  if (line == null) return "";
  if (type === "total") return `O/U ${line}`;
  return line > 0 ? `+${line}` : `${line}`;
}

/** Get override mode for a player, or "HALF" as default for QUESTIONABLE */
function getOverrideMode(
  playerName: string,
  status: string,
  overrides: Record<string, string>
): "FULL" | "HALF" | "OFF" | null {
  if (status !== "QUESTIONABLE") return null; // Only QUESTIONABLE gets toggles
  if (playerName in overrides) {
    return overrides[playerName] as "FULL" | "HALF" | "OFF";
  }
  return "HALF"; // Default
}

/** Cycle to next state: OFF → HALF → FULL → OFF */
function nextMode(current: "FULL" | "HALF" | "OFF"): "FULL" | "HALF" | "OFF" {
  if (current === "OFF") return "HALF";
  if (current === "HALF") return "FULL";
  return "OFF";
}

// ─── 3-State Toggle Button ────────────────────────────────────────

function InjuryToggle({
  mode,
  onToggle,
}: {
  mode: "FULL" | "HALF" | "OFF";
  onToggle: () => void;
}) {
  const config = {
    FULL: {
      label: "OUT",
      bg: "bg-[#FF1744]/20",
      border: "border-[#FF1744]/50",
      text: "text-[#FF1744]",
      title: "Definitely missing — full impact. Click to cycle.",
    },
    HALF: {
      label: "50%",
      bg: "bg-[#FFD600]/15",
      border: "border-[#FFD600]/40",
      text: "text-[#FFD600]",
      title: "Uncertain — 50% weighted impact. Click to cycle.",
    },
    OFF: {
      label: "IN",
      bg: "bg-[#00C853]/15",
      border: "border-[#00C853]/40",
      text: "text-[#00C853]",
      title: "Expected to play — excluded from impact. Click to cycle.",
    },
  };

  const c = config[mode];

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      title={c.title}
      className={`
        inline-flex items-center justify-center
        w-10 h-5 rounded text-[10px] font-bold
        border transition-all cursor-pointer select-none
        ${c.bg} ${c.border} ${c.text}
        hover:brightness-125 active:scale-95
      `}
    >
      {c.label}
    </button>
  );
}

// ─── Injury Row ───────────────────────────────────────────────────

function InjuryRow({
  injury,
  overrideMode,
  onToggle,
}: {
  injury: InjuryInfo;
  overrideMode: "FULL" | "HALF" | "OFF" | null;
  onToggle: (playerName: string, mode: "FULL" | "HALF" | "OFF") => void;
}) {
  const isQuestionable = overrideMode !== null;

  return (
    <div className="flex items-center gap-2">
      {/* Toggle (only for QUESTIONABLE) */}
      {isQuestionable ? (
        <InjuryToggle
          mode={overrideMode}
          onToggle={() => onToggle(injury.player_name, nextMode(overrideMode))}
        />
      ) : (
        <span className="inline-flex items-center justify-center w-10 h-5 rounded text-[10px] font-bold border bg-[#FF1744]/20 border-[#FF1744]/50 text-[#FF1744]">
          OUT
        </span>
      )}
      {/* Player name */}
      <span
        className={`text-xs ${
          overrideMode === "OFF"
            ? "text-[#64748b] line-through"
            : "text-[#94a3b8]"
        }`}
      >
        {injury.player_name}
      </span>
      {/* Reason (condensed) */}
      {injury.reason && (
        <span className="text-[10px] text-[#475569] truncate max-w-[140px]">
          {injury.reason}
        </span>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────

export default function GameCard({ game, injuryOverrides, onInjuryToggle }: GameCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const bestMarket = Object.entries(game.markets).reduce(
    (best, [, m]) => (m.edge.best_edge > (best?.edge.best_edge || 0) ? m : best),
    Object.values(game.markets)[0]
  );

  const handleCopyPrompt = async () => {
    const lines = [
      `${game.away.team} @ ${game.home.team} | ${formatET(game.tipoff)}`,
      ``,
      `ADJUSTED RATINGS:`,
      `${game.home.team} (${game.home.record}): NRtg ${game.home.season_nrtg.toFixed(1)} → ${game.home.adjusted_nrtg.toFixed(1)} (${game.home.nrtg_delta >= 0 ? "+" : ""}${game.home.nrtg_delta.toFixed(1)})`,
      `${game.away.team} (${game.away.record}): NRtg ${game.away.season_nrtg.toFixed(1)} → ${game.away.adjusted_nrtg.toFixed(1)} (${game.away.nrtg_delta >= 0 ? "+" : ""}${game.away.nrtg_delta.toFixed(1)})`,
      ``,
      `Model: Spread ${game.model.projected_spread.toFixed(1)}, Total ${game.model.projected_total.toFixed(1)}, ${game.home.team} win ${formatPct(game.model.home_win_prob)}`,
      ``,
      `EDGES:`,
      ...Object.entries(game.markets).map(
        ([type, m]) =>
          `${type}: ${m.edge.best_side} @ ${formatPrice(getBestPrice(m))} | Model: ${formatPct(m.model_probability)} | Edge: ${formatEdge(m.edge.best_edge)} | ${m.edge.verdict}`
      ),
    ];
    const success = await copyToClipboard(lines.join("\n"));
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Combine home + away injuries
  const allInjuries = [
    ...game.home.injuries.map((i) => ({ ...i, side: "home" as const })),
    ...game.away.injuries.map((i) => ({ ...i, side: "away" as const })),
  ];

  const homeQuestionable = game.home.injuries.filter((i) => i.status === "QUESTIONABLE");
  const awayQuestionable = game.away.injuries.filter((i) => i.status === "QUESTIONABLE");
  const hasQuestionable = homeQuestionable.length > 0 || awayQuestionable.length > 0;

  return (
    <div className="bg-[#111827] border border-[#1e293b] rounded-lg overflow-hidden hover:border-[#334155] transition-colors">
      {/* Collapsed View */}
      <div className="p-4 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-[#e2e8f0]">
              {game.away.team}
              <span className="text-[#64748b] mx-2">@</span>
              {game.home.team}
            </h3>
            <span className="text-xs text-[#94a3b8]">
              {game.away.record} vs {game.home.record}
            </span>
            {game.model.confidence && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-[#7C4DFF]/20 text-[#7C4DFF] font-mono">
                {game.model.confidence}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-[#64748b] font-mono">
              {formatET(game.tipoff)} / {formatSGT(game.tipoff_sgt)}
            </span>
            <svg
              className={`w-4 h-4 text-[#64748b] transition-transform ${expanded ? "rotate-180" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Compact Ratings */}
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-[#e2e8f0] font-semibold w-10">{game.home.team}</span>
            <span className="text-xs text-[#94a3b8] font-mono">NRtg:</span>
            <span className="text-sm font-mono text-[#e2e8f0]">
              {game.home.season_nrtg > 0 ? "+" : ""}{game.home.season_nrtg.toFixed(1)}
            </span>
            <span className="text-[#64748b]">→</span>
            <span className="text-sm font-mono text-[#e2e8f0] font-semibold">
              {game.home.adjusted_nrtg > 0 ? "+" : ""}{game.home.adjusted_nrtg.toFixed(1)}
            </span>
            <span className={`text-xs font-mono ${getDeltaColor(game.home.nrtg_delta)}`}>
              {getDeltaIndicator(game.home.nrtg_delta)} {game.home.nrtg_delta.toFixed(1)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-[#e2e8f0] font-semibold w-10">{game.away.team}</span>
            <span className="text-xs text-[#94a3b8] font-mono">NRtg:</span>
            <span className="text-sm font-mono text-[#e2e8f0]">
              {game.away.season_nrtg > 0 ? "+" : ""}{game.away.season_nrtg.toFixed(1)}
            </span>
            <span className="text-[#64748b]">→</span>
            <span className="text-sm font-mono text-[#e2e8f0] font-semibold">
              {game.away.adjusted_nrtg > 0 ? "+" : ""}{game.away.adjusted_nrtg.toFixed(1)}
            </span>
            <span className={`text-xs font-mono ${getDeltaColor(game.away.nrtg_delta)}`}>
              {getDeltaIndicator(game.away.nrtg_delta)} {game.away.nrtg_delta.toFixed(1)}
            </span>
          </div>
        </div>

        {/* Quick injuries — compact summary with toggle hints */}
        <div className="flex gap-4 text-xs text-[#94a3b8] mb-3">
          <span>
            {game.home.team}:{" "}
            {game.home.injuries.length > 0
              ? game.home.injuries.slice(0, 3).map((i) => {
                  const mode = getOverrideMode(i.player_name, i.status, injuryOverrides);
                  const statusLabel = mode !== null
                    ? (mode === "FULL" ? "OUT*" : mode === "OFF" ? "IN*" : "GTD")
                    : i.status;
                  return `${i.player_name} (${statusLabel})`;
                }).join(", ")
              : "Full strength"}
            {game.home.injuries.length > 3 && ` +${game.home.injuries.length - 3}`}
          </span>
          <span>
            {game.away.team}:{" "}
            {game.away.injuries.length > 0
              ? game.away.injuries.slice(0, 3).map((i) => {
                  const mode = getOverrideMode(i.player_name, i.status, injuryOverrides);
                  const statusLabel = mode !== null
                    ? (mode === "FULL" ? "OUT*" : mode === "OFF" ? "IN*" : "GTD")
                    : i.status;
                  return `${i.player_name} (${statusLabel})`;
                }).join(", ")
              : "Full strength"}
            {game.away.injuries.length > 3 && ` +${game.away.injuries.length - 3}`}
          </span>
        </div>

        {/* Best edge badge */}
        {bestMarket && (
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${getVerdictBg(bestMarket.edge.verdict)}`}>
              {bestMarket.edge.verdict}
            </span>
            <span className="text-sm text-[#e2e8f0]">
              {bestMarket.edge.best_side} {bestMarket.market_type}
            </span>
            <span className="text-sm font-mono text-[#4CAF50] font-semibold">
              {formatEdge(bestMarket.edge.best_edge)}
            </span>
          </div>
        )}
      </div>

      {/* Expanded View */}
      {expanded && (
        <div className="border-t border-[#1e293b] p-4 bg-[#0d1320]">

          {/* ── Injury Report with Toggles ── */}
          {(game.home.injuries.length > 0 || game.away.injuries.length > 0) && (
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
                  Injury Report
                </h4>
                {hasQuestionable && (
                  <span className="text-[10px] text-[#FFD600] bg-[#FFD600]/10 px-1.5 py-0.5 rounded">
                    Click GTD toggles to adjust
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-4">
                {/* Home injuries */}
                <div>
                  <p className="text-[10px] text-[#64748b] font-semibold uppercase mb-1">
                    {game.home.team}
                  </p>
                  <div className="space-y-1">
                    {game.home.injuries.map((inj) => (
                      <InjuryRow
                        key={inj.player_id || inj.player_name}
                        injury={inj}
                        overrideMode={getOverrideMode(inj.player_name, inj.status, injuryOverrides)}
                        onToggle={onInjuryToggle}
                      />
                    ))}
                    {game.home.injuries.length === 0 && (
                      <span className="text-xs text-[#4CAF50]">Full strength</span>
                    )}
                  </div>
                </div>
                {/* Away injuries */}
                <div>
                  <p className="text-[10px] text-[#64748b] font-semibold uppercase mb-1">
                    {game.away.team}
                  </p>
                  <div className="space-y-1">
                    {game.away.injuries.map((inj) => (
                      <InjuryRow
                        key={inj.player_id || inj.player_name}
                        injury={inj}
                        overrideMode={getOverrideMode(inj.player_name, inj.status, injuryOverrides)}
                        onToggle={onInjuryToggle}
                      />
                    ))}
                    {game.away.injuries.length === 0 && (
                      <span className="text-xs text-[#4CAF50]">Full strength</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Polymarket Live Prices ── */}
          <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">
            <span className="text-[#00C853]">●</span> Polymarket Live
          </h4>
          <div className="grid gap-2 mb-4">
            {Object.entries(game.markets).map(([type, m]) => {
              const homeLabel = m.home_label || game.home.team;
              const awayLabel = m.away_label || game.away.team;
              const homePrice = m.polymarket_home_yes || 0;
              const awayPrice = m.polymarket_home_no || 0;
              const bestSide = m.edge.best_side;

              return (
                <div key={type} className="flex items-center gap-3 bg-[#1a2235] rounded-lg p-3">
                  {/* Market type label */}
                  <div className="w-20 shrink-0">
                    <span className="text-xs font-semibold text-[#94a3b8] uppercase">{type}</span>
                    {m.line != null && (
                      <p className="text-[10px] text-[#64748b] font-mono">{formatLine(m.line, type)}</p>
                    )}
                  </div>

                  {/* Two-button Polymarket style */}
                  <div className="flex gap-2 flex-1">
                    <div
                      className={`flex-1 flex items-center justify-between rounded-md px-3 py-2 border transition-colors ${
                        bestSide === homeLabel
                          ? "border-[#00C853]/50 bg-[#00C853]/10"
                          : "border-[#1e293b] bg-[#111827]"
                      }`}
                    >
                      <span className={`text-sm font-medium ${bestSide === homeLabel ? "text-[#00C853]" : "text-[#e2e8f0]"}`}>
                        {homeLabel}{type === "spread" && m.line != null ? ` ${formatLine(m.line, "spread")}` : ""}
                      </span>
                      <span className={`text-sm font-mono font-bold ${bestSide === homeLabel ? "text-[#00C853]" : "text-[#e2e8f0]"}`}>
                        {Math.round(homePrice * 100)}¢
                      </span>
                    </div>

                    <div
                      className={`flex-1 flex items-center justify-between rounded-md px-3 py-2 border transition-colors ${
                        bestSide === awayLabel
                          ? "border-[#00C853]/50 bg-[#00C853]/10"
                          : "border-[#1e293b] bg-[#111827]"
                      }`}
                    >
                      <span className={`text-sm font-medium ${bestSide === awayLabel ? "text-[#00C853]" : "text-[#e2e8f0]"}`}>
                        {awayLabel}{type === "spread" && m.line != null ? ` ${formatLine(m.line != null ? -m.line : null, "spread")}` : ""}
                      </span>
                      <span className={`text-sm font-mono font-bold ${bestSide === awayLabel ? "text-[#00C853]" : "text-[#e2e8f0]"}`}>
                        {Math.round(awayPrice * 100)}¢
                      </span>
                    </div>
                  </div>

                  {/* Model vs Market comparison */}
                  <div className="w-24 text-right shrink-0">
                    <p className="text-xs text-[#64748b]">Model</p>
                    <p className="text-sm font-mono text-[#e2e8f0] font-semibold">
                      {formatPct(m.model_probability)}
                    </p>
                  </div>

                  {/* Edge + Verdict */}
                  <div className="w-28 text-right shrink-0">
                    <p className={`text-sm font-mono font-bold ${getVerdictColor(m.edge.verdict)}`}>
                      {formatEdge(m.edge.best_edge)}
                    </p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${getVerdictBg(m.edge.verdict)}`}>
                      {m.edge.verdict}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Edge Details Table (compact) ── */}
          <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-2">
            Edge Details
          </h4>
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-xs text-[#64748b] uppercase">
                  <th className="text-left py-1 pr-3">Market</th>
                  <th className="text-left py-1 pr-3">Pick</th>
                  <th className="text-right py-1 pr-3">Poly</th>
                  <th className="text-right py-1 pr-3">Model</th>
                  <th className="text-right py-1 pr-3">Edge</th>
                  <th className="text-right py-1 pr-3">EV/$</th>
                  <th className="text-right py-1 pr-3">Kelly</th>
                  <th className="text-left py-1">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(game.markets).map(([type, m]) => (
                  <tr key={type} className="border-t border-[#1e293b]">
                    <td className="py-1.5 pr-3 text-[#e2e8f0] capitalize">{type}</td>
                    <td className="py-1.5 pr-3 text-[#e2e8f0]">{m.edge.best_side}</td>
                    <td className="py-1.5 pr-3 text-right text-[#e2e8f0]">
                      {formatPrice(getBestPrice(m))}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-[#e2e8f0]">
                      {formatPct(m.model_probability)}
                    </td>
                    <td className={`py-1.5 pr-3 text-right font-semibold ${getVerdictColor(m.edge.verdict)}`}>
                      {formatEdge(m.edge.best_edge)}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-[#94a3b8]">
                      ${getBestEv(m).toFixed(2)}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-[#94a3b8]">
                      {m.edge.suggested_bet_pct.toFixed(1)}%
                    </td>
                    <td className="py-1.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${getVerdictBg(m.edge.verdict)}`}>
                        {m.edge.verdict}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Schedule Context */}
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-1">
                {game.home.team} Schedule
              </h4>
              <div className="text-xs text-[#94a3b8] space-y-0.5">
                {game.home.schedule.is_b2b && <p className="text-[#FF1744]">Back-to-back</p>}
                <p>Rest days: {game.home.schedule.rest_days}</p>
                {game.home.schedule.home_court && <p className="text-[#4CAF50]">Home court (+3.0)</p>}
              </div>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-1">
                {game.away.team} Schedule
              </h4>
              <div className="text-xs text-[#94a3b8] space-y-0.5">
                {game.away.schedule.is_b2b && <p className="text-[#FF1744]">Back-to-back</p>}
                <p>Rest days: {game.away.schedule.rest_days}</p>
                {game.away.schedule.road_trip_game > 0 && (
                  <p>Road trip game #{game.away.schedule.road_trip_game}</p>
                )}
              </div>
            </div>
          </div>

          {/* Model Details */}
          <div className="mt-4 p-3 bg-[#1a2235] rounded-md">
            <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-2">
              Model Projection
            </h4>
            <div className="grid grid-cols-4 gap-4 text-sm font-mono">
              <div>
                <span className="text-xs text-[#64748b]">NRtg Diff</span>
                <p className="text-[#e2e8f0] font-semibold">
                  {game.model.nrtg_differential > 0 ? "+" : ""}{game.model.nrtg_differential.toFixed(1)}
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">Spread</span>
                <p className="text-[#e2e8f0] font-semibold">
                  {game.home.team} {game.model.projected_spread.toFixed(1)}
                </p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">Total</span>
                <p className="text-[#e2e8f0] font-semibold">{game.model.projected_total.toFixed(1)}</p>
              </div>
              <div>
                <span className="text-xs text-[#64748b]">Win Prob</span>
                <p className="text-[#e2e8f0] font-semibold">{formatPct(game.model.home_win_prob)}</p>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3 mt-4">
            <button
              onClick={handleCopyPrompt}
              className="px-3 py-1.5 text-xs rounded bg-[#2979FF]/20 text-[#2979FF] border border-[#2979FF]/30 hover:bg-[#2979FF]/30 transition-colors font-medium"
            >
              {copied ? "Copied!" : "Copy AI Prompt"}
            </button>
            <button className="px-3 py-1.5 text-xs rounded bg-[#1a2235] text-[#94a3b8] border border-[#1e293b] hover:border-[#334155] transition-colors font-medium">
              Log Bet
            </button>
          </div>

          {/* Data Quality */}
          <div className="flex items-center gap-3 mt-3 text-xs text-[#64748b]">
            <span>Ratings: {game.data_quality?.ratings_freshness ?? "N/A"}</span>
            <span>Injuries: {game.data_quality?.injury_freshness ?? "N/A"}</span>
            <span>Prices: {game.data_quality?.price_freshness ?? "N/A"}</span>
            {(game.data_quality?.warnings?.length ?? 0) > 0 && (
              <span className="text-[#FFD600]">
                {game.data_quality.warnings.length} warning(s)
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
