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

export const api = {
  /** Get full analysis for today's games */
  getTodaysGames: () => fetchJSON<DailyAnalysis>("/games/today"),

  /** Get full analysis with injury overrides (recalculates from scratch) */
  getTodaysGamesWithOverrides: (injuryOverrides: Record<string, string>) =>
    fetchJSON<DailyAnalysis>("/games/today", {
      method: "POST",
      body: JSON.stringify({ injury_overrides: injuryOverrides }),
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
};
