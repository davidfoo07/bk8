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

export interface GameAnalysis {
  game_id: string;
  tipoff: string | null;
  tipoff_sgt: string | null;
  venue: string;
  home: TeamGameData;
  away: TeamGameData;
  model: GamePrediction;
  markets: Record<string, MarketEdge>;
  data_quality: DataQuality;
}

export interface TopEdge {
  game: string;
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
