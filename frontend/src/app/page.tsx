"use client";

import { useEffect, useState } from "react";
import Header from "@/components/Header";
import TopEdges from "@/components/TopEdges";
import GameCard from "@/components/GameCard";
import EmptyState from "@/components/EmptyState";
import type { DailyAnalysis } from "@/types/api";
import { api } from "@/lib/api";
import { copyToClipboard } from "@/lib/utils";

// Sample data for development (matching the backend sample)
const SAMPLE_DATA: DailyAnalysis = {
  date: "2026-04-07",
  timezone_note: "All times in US Eastern. Operator is UTC+8.",
  games_count: 1,
  games: [
    {
      game_id: "2026-04-07_CLE_MEM",
      tipoff: "2026-04-07T23:30:00Z",
      tipoff_sgt: "2026-04-08T07:30:00+08:00",
      venue: "Rocket Mortgage FieldHouse",
      home: {
        team: "CLE",
        full_name: "Cleveland Cavaliers",
        record: "62-18",
        seed: 1,
        motivation: "REST_EXPECTED",
        season_ortg: 118.5,
        season_drtg: 108.2,
        season_nrtg: 10.3,
        adjusted_ortg: 116.1,
        adjusted_drtg: 110.0,
        adjusted_nrtg: 6.1,
        nrtg_delta: -4.2,
        injuries: [
          {
            player_name: "Evan Mobley",
            player_id: "1631096",
            team: "CLE",
            status: "OUT",
            reason: "Rest",
            source: "NBA Official",
            last_updated: null,
            confirmed_at: null,
            impact_rating: "HIGH",
          },
        ],
        schedule: {
          is_b2b: false,
          is_3_in_4: false,
          is_4_in_6: false,
          rest_days: 2,
          road_trip_game: 0,
          home_court: true,
          travel_distance_miles: 0,
        },
      },
      away: {
        team: "MEM",
        full_name: "Memphis Grizzlies",
        record: "48-32",
        seed: 4,
        motivation: "FIGHTING",
        season_ortg: 113.8,
        season_drtg: 111.5,
        season_nrtg: 2.3,
        adjusted_ortg: 113.8,
        adjusted_drtg: 111.5,
        adjusted_nrtg: 2.3,
        nrtg_delta: 0.0,
        injuries: [],
        schedule: {
          is_b2b: true,
          is_3_in_4: false,
          is_4_in_6: false,
          rest_days: 0,
          road_trip_game: 3,
          home_court: false,
          travel_distance_miles: 0,
        },
      },
      model: {
        nrtg_differential: 3.8,
        schedule_adjustment: -2.5,
        home_court: 3.0,
        projected_spread: -4.3,
        projected_total: 221.5,
        home_win_prob: 0.635,
        confidence: "MEDIUM",
      },
      markets: {
        moneyline: {
          market_type: "moneyline",
          line: null,
          polymarket_home_yes: 0.72,
          polymarket_home_no: 0.28,
          model_probability: 0.635,
          edge: {
            yes_edge: -0.085,
            no_edge: 0.085,
            yes_ev: -0.118,
            no_ev: 0.304,
            best_side: "NO",
            best_edge: 0.085,
            verdict: "BUY",
            kelly_fraction: 0.041,
            suggested_bet_pct: 4.1,
          },
        },
        spread: {
          market_type: "spread",
          line: -8.5,
          polymarket_home_yes: 0.52,
          polymarket_home_no: 0.48,
          model_probability: 0.44,
          edge: {
            yes_edge: -0.08,
            no_edge: 0.08,
            yes_ev: -0.154,
            no_ev: 0.167,
            best_side: "NO",
            best_edge: 0.08,
            verdict: "BUY",
            kelly_fraction: 0.038,
            suggested_bet_pct: 3.8,
          },
        },
        total: {
          market_type: "total",
          line: 224.5,
          polymarket_home_yes: 0.55,
          polymarket_home_no: 0.45,
          model_probability: 0.48,
          edge: {
            yes_edge: -0.07,
            no_edge: 0.07,
            yes_ev: -0.127,
            no_ev: 0.156,
            best_side: "NO",
            best_edge: 0.07,
            verdict: "BUY",
            kelly_fraction: 0.033,
            suggested_bet_pct: 3.3,
          },
        },
      },
      data_quality: {
        ratings_freshness: "FRESH",
        injury_freshness: "FRESH",
        price_freshness: "FRESH",
        cross_source_validated: true,
        warnings: [],
      },
    },
  ],
  top_edges: [
    {
      game: "MEM @ CLE",
      market: "moneyline",
      selection: "MEM moneyline",
      price: 0.28,
      model_prob: 0.365,
      edge: 0.085,
      verdict: "BUY",
    },
    {
      game: "MEM @ CLE",
      market: "spread",
      selection: "MEM spread",
      price: 0.48,
      model_prob: 0.56,
      edge: 0.08,
      verdict: "BUY",
    },
    {
      game: "MEM @ CLE",
      market: "total",
      selection: "Under total",
      price: 0.45,
      model_prob: 0.52,
      edge: 0.07,
      verdict: "BUY",
    },
  ],
};

export default function Dashboard() {
  const [data, setData] = useState<DailyAnalysis>(SAMPLE_DATA);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiPromptCopied, setAiPromptCopied] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const result = await api.getTodaysGames();
        setData(result);
        setError(null);
      } catch (err) {
        console.warn("API not available, using sample data:", err);
        // Keep sample data as fallback
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleCopyFullSlate = async () => {
    try {
      const result = await api.getAiPrompt();
      await copyToClipboard(result.prompt);
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    } catch {
      // Fallback: generate from local data
      const lines = data.games.map(
        (g) =>
          `${g.away.team} @ ${g.home.team}: ${Object.entries(g.markets)
            .map(([t, m]) => `${t} ${m.edge.best_side} ${(m.edge.best_edge * 100).toFixed(1)}%`)
            .join(" | ")}`
      );
      await copyToClipboard(lines.join("\n"));
      setAiPromptCopied(true);
      setTimeout(() => setAiPromptCopied(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Loading state */}
        {loading && (
          <div className="text-center py-10 text-[#94a3b8]">Loading analysis...</div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-[#FF1744]/10 border border-[#FF1744]/30 rounded-lg p-4 mb-6 text-sm text-[#FF1744]">
            {error}
          </div>
        )}

        {/* Top Edges Banner */}
        <TopEdges edges={data.top_edges} />

        {/* Copy Full Slate Button */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
            Games ({data.games_count})
          </h2>
          <button
            onClick={handleCopyFullSlate}
            className="px-3 py-1.5 text-xs rounded bg-[#2979FF]/20 text-[#2979FF] border border-[#2979FF]/30 hover:bg-[#2979FF]/30 transition-colors font-medium"
          >
            {aiPromptCopied ? "Copied!" : "Copy Full Slate AI Prompt"}
          </button>
        </div>

        {/* Game Cards */}
        {data.games.length > 0 ? (
          <div className="space-y-4">
            {data.games.map((game) => (
              <GameCard key={game.game_id} game={game} />
            ))}
          </div>
        ) : (
          <EmptyState />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#1e293b] mt-12 py-4 text-center text-xs text-[#64748b]">
        CourtEdge v0.1 — Lineup-adjusted NBA analytics for Polymarket
      </footer>
    </div>
  );
}
