/** TypeScript types matching the backend Pydantic schemas. */

export interface InjuryInfo {
  player_name: string;
  player_id: string;
  team: string;
  status: string;
  reason: string | null;
  source: string;
  last_updated: string | null;
  confirmed_at: string | null;
  impact_rating: string;
}

export interface ScheduleContext {
  is_b2b: boolean;
  is_3_in_4: boolean;
  is_4_in_6: boolean;
  rest_days: number;
  road_trip_game: number;
  home_court: boolean;
  travel_distance_miles: number;
}

export interface EdgeResult {
  yes_edge: number;
  no_edge: number;
  yes_ev: number;
  no_ev: number;
  best_side: "YES" | "NO";
  best_edge: number;
  verdict: "STRONG BUY" | "BUY" | "LEAN" | "NO EDGE";
  kelly_fraction: number;
  suggested_bet_pct: number;
}

export interface MarketEdge {
  market_type: string;
  line: number | null;
  polymarket_home_yes: number | null;
  polymarket_home_no: number | null;
  home_label: string | null;
  away_label: string | null;
  model_probability: number;
  edge: EdgeResult;
}

export interface GamePrediction {
  nrtg_differential: number;
  schedule_adjustment: number;
  home_court: number;
  projected_spread: number;
  projected_total: number;
  home_win_prob: number;
  confidence: "HIGH" | "MEDIUM" | "LOW";
}

export interface DataQuality {
  ratings_freshness: "FRESH" | "STALE" | "MISSING";
  injury_freshness: "FRESH" | "STALE" | "MISSING";
  price_freshness: "FRESH" | "STALE" | "MISSING";
  cross_source_validated: boolean;
  warnings: string[];
}

export interface TeamGameData {
  team: string;
  full_name: string;
  record: string;
  seed: number | null;
  motivation: string;
  season_ortg: number;
  season_drtg: number;
  season_nrtg: number;
  adjusted_ortg: number;
  adjusted_drtg: number;
  adjusted_nrtg: number;
  nrtg_delta: number;
  injuries: InjuryInfo[];
  schedule: ScheduleContext;
}

export interface LivePlayerStats {
  name: string;
  player_id: string;
  position: string;
  team: string;
  minutes: string;
  points: number;
  rebounds: number;
  assists: number;
  steals: number;
  blocks: number;
  turnovers: number;
  fouls: number;
  plus_minus: number;
  fg_pct: number;
  three_pct: number;
  ft_pct: number;
}

export interface LiveGameState {
  game_status: 1 | 2 | 3;
  game_status_text: string;
  period: number;
  game_clock: string;
  home_score: number;
  away_score: number;
  nba_game_id: string;
  home_periods: { period: number; score: number }[];
  away_periods: { period: number; score: number }[];
  home_leader: { name?: string; points?: number; rebounds?: number; assists?: number };
  away_leader: { name?: string; points?: number; rebounds?: number; assists?: number };
  home_players: LivePlayerStats[];
  away_players: LivePlayerStats[];
}

export interface LivePrediction {
  home_win_prob: number;
  pre_game_home_win_prob: number;
  projected_final_margin: number;
  live_margin: number;
  time_remaining_pct: number;
  is_final: boolean;
  home_won: boolean | null;
}

export interface GameAnalysis {
  game_id: string;
  tipoff: string | null;
  tipoff_sgt: string | null;
  venue: string;
  home: TeamGameData;
  away: TeamGameData;
  model: GamePrediction;
  live: LiveGameState;
  live_prediction: LivePrediction | null;
  markets: Record<string, MarketEdge>;
  data_quality: DataQuality;
}

export interface TopEdge {
  game: string;
  game_id: string;
  market: string;
  selection: string;
  price: number;
  model_prob: number;
  edge: number;
  verdict: string;
}

export interface DailyAnalysis {
  date: string;
  timezone_note: string;
  games_count: number;
  games: GameAnalysis[];
  top_edges: TopEdge[];
}

export interface BetCreate {
  game_id: string;
  prediction_id?: number;
  market_type: string;
  selection: string;
  side: "YES" | "NO";
  entry_price: number;
  model_probability: number;
  edge_at_entry: number;
  amount_usd: number;
  kelly_fraction: number;
  notes: string;
  system_aligned: boolean;
}

export interface BetResponse {
  id: number;
  game_id: string;
  market_type: string;
  selection: string;
  side: string;
  entry_price: number;
  model_probability: number;
  edge_at_entry: number;
  amount_usd: number;
  kelly_fraction: number;
  result: string | null;
  pnl: number | null;
  system_aligned: boolean;
  placed_at: string;
  resolved_at: string | null;
}

export interface BetHistoryResponse {
  total_bets: number;
  wins: number;
  losses: number;
  pushes: number;
  pending: number;
  total_pnl: number;
  win_rate: number;
  roi: number;
  bets: BetResponse[];
}
