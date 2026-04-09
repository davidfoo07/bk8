"use client";

import { useEffect, useState } from "react";
import type { GameAnalysis, InjuryInfo, LivePlayerStats } from "@/types/api";
import BetLogModal from "@/components/BetLogModal";
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
  forceExpanded?: boolean;
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

/** Get the model probability for the PICKED side (flip if pick is away/NO) */
function getPickProb(m: GameAnalysis["markets"][string]): number {
  return isHomeSide(m) ? m.model_probability : 1 - m.model_probability;
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

/** Build a short pick label like "Grizzlies +21.5" or "Under" */
function getPickLabel(m: GameAnalysis["markets"][string], type: string): string {
  const side = m.edge.best_side;
  if (type === "spread" && m.line != null) {
    const isHome = side === m.home_label;
    const line = isHome ? m.line : -m.line;
    const lineStr = line > 0 ? `+${line}` : `${line}`;
    return `${side} ${lineStr}`;
  }
  return side;
}

/** Get override mode for a player, or "HALF" as default for QUESTIONABLE */
function getOverrideMode(
  playerName: string,
  status: string,
  overrides: Record<string, string>
): "FULL" | "HALF" | "OFF" | null {
  if (status !== "QUESTIONABLE") return null;
  if (playerName in overrides) {
    return overrides[playerName] as "FULL" | "HALF" | "OFF";
  }
  return "HALF";
}

/** Cycle to next state: OFF -> HALF -> FULL -> OFF */
function nextMode(current: "FULL" | "HALF" | "OFF"): "FULL" | "HALF" | "OFF" {
  if (current === "OFF") return "HALF";
  if (current === "HALF") return "FULL";
  return "OFF";
}

/** Format leader stats line e.g. "J. Morant: 25pts 5reb 8ast" */
function formatLeader(leader: { name?: string; points?: number; rebounds?: number; assists?: number }): string | null {
  if (!leader.name) return null;
  const parts: string[] = [];
  if (leader.points != null) parts.push(`${leader.points}pts`);
  if (leader.rebounds != null) parts.push(`${leader.rebounds}reb`);
  if (leader.assists != null) parts.push(`${leader.assists}ast`);
  return `${leader.name}: ${parts.join(" ")}`;
}

/** Parse minutes string "25:30" to a sortable number */
function parseMinutes(min: string): number {
  if (!min) return 0;
  const parts = min.split(":");
  return parseInt(parts[0] || "0", 10) + (parseInt(parts[1] || "0", 10) / 60);
}

/** Get the favored team name based on win prob */
function getFavoredTeam(game: GameAnalysis): { name: string; prob: number } {
  if (game.model.home_win_prob >= 0.5) {
    return { name: game.home.team, prob: game.model.home_win_prob };
  }
  return { name: game.away.team, prob: 1 - game.model.home_win_prob };
}

// --- 3-State Toggle Button ---

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

// --- Injury Row ---

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
      <span
        className={`text-xs ${
          overrideMode === "OFF"
            ? "text-[#64748b] line-through"
            : "text-[#94a3b8]"
        }`}
      >
        {injury.player_name}
      </span>
      {injury.reason && (
        <span className="text-[10px] text-[#475569] truncate max-w-[140px]">
          {injury.reason}
        </span>
      )}
    </div>
  );
}

// --- Game Status Badge ---

function GameStatusBadge({ game }: { game: GameAnalysis }) {
  const live = game.live;
  if (!live) return null;

  if (live.game_status === 1) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded bg-[#2979FF]/15 text-[#2979FF] border border-[#2979FF]/30 font-medium">
        SCHEDULED
      </span>
    );
  }

  if (live.game_status === 2) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded bg-[#FF1744]/15 text-[#FF1744] border border-[#FF1744]/30 font-semibold">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#FF1744] opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-[#FF1744]" />
        </span>
        LIVE {live.game_status_text}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded bg-[#64748b]/15 text-[#94a3b8] border border-[#64748b]/30 font-medium">
      FINAL
    </span>
  );
}

// --- Live Score Display ---

function LiveScoreDisplay({ game }: { game: GameAnalysis }) {
  const live = game.live;
  if (!live || live.game_status === 1) return null;

  const homeWon = live.game_status === 3 && live.home_score > live.away_score;
  const awayWon = live.game_status === 3 && live.away_score > live.home_score;

  return (
    <div className="flex flex-col items-center py-2">
      <div className="flex items-center gap-3 text-xl font-mono font-bold">
        <span className={awayWon ? "text-[#00C853]" : "text-[#e2e8f0]"}>
          {game.away.team} {live.away_score}
        </span>
        <span className="text-[#64748b] text-base">—</span>
        <span className={homeWon ? "text-[#00C853]" : "text-[#e2e8f0]"}>
          {live.home_score} {game.home.team}
        </span>
      </div>
      {live.game_status === 2 && live.game_clock && (
        <span className="text-xs text-[#94a3b8] font-mono mt-0.5">
          Q{live.period} {live.game_clock}
        </span>
      )}
      {live.game_status === 3 && (
        <span className="text-[10px] text-[#64748b] font-medium mt-0.5">
          {homeWon ? `${game.home.team} WIN` : awayWon ? `${game.away.team} WIN` : "TIE"}
        </span>
      )}
    </div>
  );
}

// --- Game Leaders ---

function GameLeaders({ game }: { game: GameAnalysis }) {
  const live = game.live;
  if (!live || live.game_status === 1) return null;
  const homeLine = formatLeader(live.home_leader);
  const awayLine = formatLeader(live.away_leader);
  if (!homeLine && !awayLine) return null;

  return (
    <div className="flex justify-center gap-4 text-[11px] text-[#94a3b8] font-mono">
      {awayLine && <span>{awayLine}</span>}
      {awayLine && homeLine && <span className="text-[#475569]">/</span>}
      {homeLine && <span>{homeLine}</span>}
    </div>
  );
}

// --- Win Probability Bar (with explicit team names) ---

function WinProbBar({ game }: { game: GameAnalysis }) {
  const live = game.live;
  const livePred = game.live_prediction;

  let barProb = game.model.home_win_prob;
  let showLiveProb = false;

  if (livePred) {
    if (live?.game_status === 3) {
      barProb = livePred.home_won === true ? 1 : livePred.home_won === false ? 0 : barProb;
    } else if (live?.game_status === 2) {
      barProb = livePred.home_win_prob;
    }
    showLiveProb = true;
  }

  const homePct = Math.round(barProb * 100);
  const awayPct = 100 - homePct;

  // Determine favored team for pre-game label
  const preGameFavored = game.model.home_win_prob >= 0.5
    ? { name: game.home.team, prob: game.model.home_win_prob }
    : { name: game.away.team, prob: 1 - game.model.home_win_prob };

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between text-[10px] text-[#94a3b8] mb-1">
        <span className="font-semibold">{game.away.team} {awayPct}%</span>
        <div className="flex items-center gap-3">
          <span className="text-[#64748b]">
            Pre-game: {preGameFavored.name} {formatPct(preGameFavored.prob)}
          </span>
          {showLiveProb && livePred && (
            <span className="text-[#FF1744] font-semibold">
              Live: {game.home.team} {formatPct(livePred.home_win_prob)}
            </span>
          )}
        </div>
        <span className="font-semibold">{game.home.team} {homePct}%</span>
      </div>
      <div className="h-2 rounded-full bg-[#1e293b] overflow-hidden flex">
        <div
          className="h-full bg-gradient-to-r from-[#2979FF] to-[#2979FF]/70 transition-all duration-500"
          style={{ width: `${awayPct}%` }}
        />
        <div
          className="h-full bg-gradient-to-r from-[#00C853]/70 to-[#00C853] transition-all duration-500"
          style={{ width: `${homePct}%` }}
        />
      </div>
    </div>
  );
}

// --- Live Box Score ---

function LiveBoxScore({ players, teamName }: { players: LivePlayerStats[]; teamName: string }) {
  const sorted = [...players]
    .sort((a, b) => parseMinutes(b.minutes) - parseMinutes(a.minutes))
    .slice(0, 8);

  if (sorted.length === 0) return null;

  return (
    <div className="mb-3">
      <p className="text-[10px] text-[#64748b] font-semibold uppercase mb-1">{teamName}</p>
      <table className="w-full text-[11px] font-mono">
        <thead>
          <tr className="text-[10px] text-[#64748b] uppercase">
            <th className="text-left py-0.5 pr-2">Player</th>
            <th className="text-right py-0.5 px-1">MIN</th>
            <th className="text-right py-0.5 px-1">PTS</th>
            <th className="text-right py-0.5 px-1">REB</th>
            <th className="text-right py-0.5 px-1">AST</th>
            <th className="text-right py-0.5 px-1">+/-</th>
            <th className="text-right py-0.5 pl-1">FLS</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => {
            const foulTrouble = p.fouls >= 4;
            return (
              <tr
                key={p.player_id || p.name}
                className={`border-t border-[#1e293b] ${foulTrouble ? "bg-[#FFD600]/10" : ""}`}
              >
                <td className={`py-0.5 pr-2 text-left truncate max-w-[120px] ${foulTrouble ? "text-[#FFD600]" : "text-[#e2e8f0]"}`}>
                  {p.name}
                </td>
                <td className="py-0.5 px-1 text-right text-[#94a3b8]">{p.minutes}</td>
                <td className="py-0.5 px-1 text-right text-[#e2e8f0] font-semibold">{p.points}</td>
                <td className="py-0.5 px-1 text-right text-[#94a3b8]">{p.rebounds}</td>
                <td className="py-0.5 px-1 text-right text-[#94a3b8]">{p.assists}</td>
                <td className={`py-0.5 px-1 text-right ${p.plus_minus > 0 ? "text-[#00C853]" : p.plus_minus < 0 ? "text-[#FF1744]" : "text-[#94a3b8]"}`}>
                  {p.plus_minus > 0 ? "+" : ""}{p.plus_minus}
                </td>
                <td className={`py-0.5 pl-1 text-right ${foulTrouble ? "text-[#FFD600] font-bold" : "text-[#94a3b8]"}`}>
                  {p.fouls}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- Main Component ---

export default function GameCard({ game, injuryOverrides, onInjuryToggle, forceExpanded }: GameCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // Allow parent to force-expand this card (e.g. when clicked from summary table)
  useEffect(() => {
    if (forceExpanded) setExpanded(true);
  }, [forceExpanded]);
  const [showBetModal, setShowBetModal] = useState(false);

  const live = game.live;
  const isLive = live?.game_status === 2;
  const isFinal = live?.game_status === 3;
  const isScheduled = !live || live.game_status === 1;

  const bestMarket = Object.entries(game.markets).reduce(
    (best, [, m]) => (m.edge.best_edge > (best?.edge.best_edge || 0) ? m : best),
    Object.values(game.markets)[0]
  );

  // Determine favored team for display
  const favored = getFavoredTeam(game);

  const handleCopyPrompt = async () => {
    const lines = [
      `${game.away.team} @ ${game.home.team} | ${formatET(game.tipoff)}`,
      ``,
      `ADJUSTED RATINGS:`,
      `${game.home.team} (${game.home.record}): NRtg ${game.home.season_nrtg.toFixed(1)} → ${game.home.adjusted_nrtg.toFixed(1)} (${game.home.nrtg_delta >= 0 ? "+" : ""}${game.home.nrtg_delta.toFixed(1)})`,
      `${game.away.team} (${game.away.record}): NRtg ${game.away.season_nrtg.toFixed(1)} → ${game.away.adjusted_nrtg.toFixed(1)} (${game.away.nrtg_delta >= 0 ? "+" : ""}${game.away.nrtg_delta.toFixed(1)})`,
      ``,
      `Model: ${favored.name} favored at ${formatPct(favored.prob)}, Spread ${game.model.projected_spread.toFixed(1)}, Total ${game.model.projected_total.toFixed(1)}`,
      ``,
      `EDGES:`,
      ...Object.entries(game.markets).map(
        ([type, m]) =>
          `${type}: ${getPickLabel(m, type)} | Model: ${formatPct(getPickProb(m))} | Poly: ${formatPrice(getBestPrice(m))} | Edge: ${formatEdge(m.edge.best_edge)} | ${m.edge.verdict}`
      ),
    ];
    const success = await copyToClipboard(lines.join("\n"));
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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
            <GameStatusBadge game={game} />
          </div>
          <div className="flex items-center gap-4">
            {isScheduled && (
              <span className="text-xs text-[#64748b] font-mono">
                {formatET(game.tipoff)} / {formatSGT(game.tipoff_sgt)}
              </span>
            )}
            <svg
              className={`w-4 h-4 text-[#64748b] transition-transform ${expanded ? "rotate-180" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Live Score (LIVE or FINAL) */}
        {(isLive || isFinal) && (
          <>
            <LiveScoreDisplay game={game} />
            <GameLeaders game={game} />
          </>
        )}

        {/* Win Probability Bar */}
        <WinProbBar game={game} />

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

        {/* Quick injuries */}
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

        {/* Best edge badge — hide for FINAL games */}
        {bestMarket && !isFinal && (
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
        {isFinal && (
          <div className="flex items-center gap-2">
            <span className="text-xs px-2 py-0.5 rounded border border-[#64748b]/30 bg-[#64748b]/10 text-[#94a3b8] font-semibold">
              RESOLVED
            </span>
            <span className="text-xs text-[#64748b]">Markets closed</span>
          </div>
        )}
      </div>

      {/* Expanded View */}
      {expanded && (
        <div className="border-t border-[#1e293b] p-4 bg-[#0d1320]">

          {/* Live Box Score (LIVE games only) */}
          {isLive && live && live.home_players.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-2">
                <span className="relative inline-flex h-2 w-2 mr-1.5 align-middle">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#FF1744] opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#FF1744]" />
                </span>
                Live Box Score
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <LiveBoxScore players={live.home_players} teamName={game.home.team} />
                <LiveBoxScore players={live.away_players} teamName={game.away.team} />
              </div>
            </div>
          )}

          {/* Injury Report with Toggles */}
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

          {/* Polymarket Live Prices — hidden for FINAL games */}
          {!isFinal && (
            <>
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
                  const pickLabel = getPickLabel(m, type);
                  const pickProb = getPickProb(m);

                  return (
                    <div key={type} className="flex items-center gap-3 bg-[#1a2235] rounded-lg p-3">
                      <div className="w-20 shrink-0">
                        <span className="text-xs font-semibold text-[#94a3b8] uppercase">{type}</span>
                        {m.line != null && (
                          <p className="text-[10px] text-[#64748b] font-mono">{formatLine(m.line, type)}</p>
                        )}
                      </div>

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

                      <div className="w-44 shrink-0">
                        <div className={`rounded-md px-3 py-1.5 text-right ${
                          m.edge.verdict === "STRONG BUY" ? "bg-[#00C853]/10" :
                          m.edge.verdict === "BUY" ? "bg-[#4CAF50]/10" :
                          "bg-[#1e293b]/50"
                        }`}>
                          <div className="flex items-center justify-end gap-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${getVerdictBg(m.edge.verdict)}`}>
                              {m.edge.verdict}
                            </span>
                            <span className={`text-sm font-mono font-bold ${getVerdictColor(m.edge.verdict)}`}>
                              {formatEdge(m.edge.best_edge)}
                            </span>
                          </div>
                          <p className={`text-xs font-semibold mt-0.5 ${getVerdictColor(m.edge.verdict)}`}>
                            {pickLabel}
                          </p>
                          <p className="text-[10px] text-[#64748b] font-mono">
                            Model {formatPct(pickProb)} vs {formatPrice(getBestPrice(m))}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* FINAL: show resolved markets summary */}
          {isFinal && (
            <div className="mb-4 p-3 bg-[#1a2235]/50 rounded-lg border border-[#1e293b]">
              <h4 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-2">
                Markets — Resolved
              </h4>
              <div className="grid gap-1">
                {Object.entries(game.markets).map(([type, m]) => (
                  <div key={type} className="flex items-center gap-3 text-xs text-[#64748b]">
                    <span className="uppercase w-16">{type}</span>
                    <span>{m.edge.best_side}</span>
                    <span className="font-mono">{formatEdge(m.edge.best_edge)}</span>
                    <span className="px-1.5 py-0.5 rounded bg-[#64748b]/10 border border-[#64748b]/20 text-[10px]">
                      {m.edge.verdict}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Edge Details Table — hidden for FINAL */}
          {!isFinal && (
            <>
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
                        <td className="py-1.5 pr-3 text-[#e2e8f0]">{getPickLabel(m, type)}</td>
                        <td className="py-1.5 pr-3 text-right text-[#e2e8f0]">
                          {formatPrice(getBestPrice(m))}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-[#e2e8f0]">
                          {formatPct(getPickProb(m))}
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
            </>
          )}

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

          {/* Model Details — now with explicit team names */}
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
                <p className="text-[#e2e8f0] font-semibold">
                  {favored.name} {formatPct(favored.prob)}
                </p>
              </div>
            </div>
          </div>

          {/* Action buttons — hide Log Bet for FINAL games */}
          <div className="flex gap-3 mt-4">
            <button
              onClick={handleCopyPrompt}
              className="px-3 py-1.5 text-xs rounded bg-[#2979FF]/20 text-[#2979FF] border border-[#2979FF]/30 hover:bg-[#2979FF]/30 transition-colors font-medium"
            >
              {copied ? "Copied!" : "Copy AI Prompt"}
            </button>
            {!isFinal && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowBetModal(true);
                }}
                className="px-3 py-1.5 text-xs rounded bg-[#00C853]/20 text-[#00C853] border border-[#00C853]/30 hover:bg-[#00C853]/30 transition-colors font-medium"
              >
                Log Bet
              </button>
            )}
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

      {/* Bet Logging Modal */}
      {showBetModal && (
        <BetLogModal
          game={game}
          onClose={() => setShowBetModal(false)}
          onBetPlaced={() => setShowBetModal(false)}
        />
      )}
    </div>
  );
}
