/** API client for CourtEdge backend. */

import type { DailyAnalysis, GameAnalysis, BetCreate, BetResponse, BetHistoryResponse } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "Unknown error");
    throw new Error(`API Error ${res.status}: ${errorBody}`);
  }

  return res.json() as Promise<T>;
}

export interface SavedDateEntry {
  date: string;
  games_count: number;
  saved_at: string | null;
  file_size_kb: number;
}

export interface ScheduleEntry {
  date: string;
  games_count: number;
  is_today: boolean;
}

export interface SimBet {
  game: string;
  market_type: string;
  selection: string;
  side: string;
  verdict: string;
  entry_price: number;
  model_prob: number;
  edge: number;
  kelly_fraction: number;
  flat_result: string | null;
  flat_pnl: number;
  kelly_amount: number;
  kelly_result: string | null;
  kelly_pnl: number;
}

export interface DailySimulation {
  date: string;
  total_bets: number;
  flat_wins: number;
  flat_losses: number;
  flat_record: string;
  flat_pnl: number;
  flat_roi: number;
  kelly_wins: number;
  kelly_losses: number;
  kelly_pnl: number;
  kelly_roi: number;
  bets: SimBet[];
}

export interface MarketCalibration {
  market_type: string;
  n: number;
  model_brier: number | null;
  market_brier: number | null;
  model_log_loss: number | null;
  market_log_loss: number | null;
  /** model − market; negative means the model forecast better */
  brier_diff: number | null;
  brier_diff_se: number | null;
  avg_abs_disagreement: number | null;
  conclusion: "too_few" | "model_better" | "market_better" | "no_difference";
}

export interface BetRecord {
  market_type: string;
  n: number;
  wins: number;
  hit_rate: number | null;
  avg_price: number | null;
  pnl: number;
  roi: number | null;
  roi_se: number | null;
}

export interface ModelEvaluation {
  dates: string[];
  graded_games: number;
  min_games: number;
  conclusive: boolean;
  calibration: MarketCalibration[];
  bets: BetRecord[];
  clv: { supported: boolean; reason: string; needed: string };
}

export const api = {
  /** Get full analysis for today's games */
  getTodaysGames: () => fetchJSON<DailyAnalysis>("/games/today"),

  /** Today's slate + upcoming dates with games (for the dashboard date picker) */
  getSchedule: () => fetchJSON<ScheduleEntry[]>("/games/schedule"),

  /** Full analysis for today's slate or an upcoming date (YYYY-MM-DD) */
  getGamesForDate: (date: string) => fetchJSON<DailyAnalysis>(`/games/date/${date}`),

  /** Recalculate a date's slate (default: today) with injury overrides */
  getGamesWithOverrides: (injuryOverrides: Record<string, string>, gameDate?: string | null) =>
    fetchJSON<DailyAnalysis>("/games/today", {
      method: "POST",
      body: JSON.stringify({ injury_overrides: injuryOverrides, game_date: gameDate ?? null }),
    }),

  /** Get AI-formatted prompt for today's games */
  getAiPrompt: () => fetchJSON<{ prompt: string; format: string; date: string }>("/games/today/ai-prompt"),

  /** Get detailed analysis for a specific game */
  getGame: (gameId: string) => fetchJSON<GameAnalysis>(`/games/${gameId}`),

  /** Get upcoming games (today + saved predictions for future games) */
  getUpcomingGames: () => fetchJSON<DailyAnalysis>("/games/upcoming"),

  /** List all saved prediction dates */
  getHistoryDates: () => fetchJSON<SavedDateEntry[]>("/games/history"),

  /** Load saved predictions for a specific date */
  getHistoryForDate: (date: string) => fetchJSON<DailyAnalysis>(`/games/history/${date}`),

  /** Log a new bet */
  createBet: (bet: BetCreate) =>
    fetchJSON<BetResponse>("/bets", {
      method: "POST",
      body: JSON.stringify(bet),
    }),

  /** Get bet history with stats */
  getBetHistory: () => fetchJSON<BetHistoryResponse>("/bets/history"),

  /** Auto-resolve pending bets against actual NBA scores */
  resolveBets: () =>
    fetchJSON<{ resolved: number; wins: number; losses: number; total_pnl: number }>(
      "/bets/resolve",
      { method: "POST" },
    ),

  /** Model vs Polymarket calibration + BUY-verdict ROI over all graded History */
  getModelEvaluation: () => fetchJSON<ModelEvaluation>("/results/evaluation"),

  /** List all dates available for simulation */
  getSimulationDates: () => fetchJSON<SavedDateEntry[]>("/simulation/"),

  /** Run simulation for a specific date */
  getSimulation: (date: string) => fetchJSON<DailySimulation>(`/simulation/${date}`),
};
