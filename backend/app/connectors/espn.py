"""ESPN public API connector — schedule, live scores, box scores, rosters.

Primary source for everything that changes during a game.  stats.nba.com blocks
IPs that poll it (403 from Akamai); ESPN's site API doesn't.
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector
from app.connectors.injuries import ESPN_ABBR_FIX, ESPN_TEAM_TO_ABBR

_ET = ZoneInfo("America/New_York")
_STATE_TO_STATUS = {"pre": 1, "in": 2, "post": 3}

# ESPN team id → NBA abbreviation (for roster URLs)
ESPN_TEAM_ID_TO_ABBR: dict[int, str] = {
    1: "ATL", 2: "BOS", 17: "BKN", 30: "CHA", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GSW", 10: "HOU", 11: "IND", 12: "LAC", 13: "LAL", 29: "MEM", 14: "MIA",
    15: "MIL", 16: "MIN", 3: "NOP", 18: "NYK", 25: "OKC", 19: "ORL", 20: "PHI", 21: "PHX",
    22: "POR", 23: "SAC", 24: "SAS", 28: "TOR", 26: "UTA", 27: "WAS",
}
ABBR_TO_ESPN_TEAM_ID = {abbr: tid for tid, abbr in ESPN_TEAM_ID_TO_ABBR.items()}


def espn_abbr(team: dict[str, Any]) -> str | None:
    """NBA abbreviation for an ESPN team object."""
    abbr = (team.get("abbreviation") or "").upper()
    abbr = ESPN_ABBR_FIX.get(abbr, abbr)
    if abbr in ABBR_TO_ESPN_TEAM_ID:
        return abbr
    return ESPN_TEAM_TO_ABBR.get(team.get("displayName", ""))


def _clock(display: str | None) -> str:
    """ESPN shows '3:30', or plain seconds ('45.2') in the last minute → 'M:SS'."""
    display = (display or "").strip()
    if not display or ":" in display:
        return display
    try:
        secs = float(display)
    except ValueError:
        return ""
    return f"{int(secs // 60)}:{int(secs % 60):02d}"


def _status_text(state: str, status: dict[str, Any], tipoff: datetime | None) -> str:
    status_type = status.get("type") or {}
    if state == "pre" and tipoff is not None:
        et = tipoff.astimezone(_ET)
        return f"{et.strftime('%I:%M %p').lstrip('0').lower()} ET"
    short = status_type.get("shortDetail") or status_type.get("description") or ""
    if state != "in":
        return short
    # ESPN shows "0.0 - 3rd" between quarters; say it properly.
    if status_type.get("name") == "STATUS_HALFTIME":
        return "Halftime"
    period_label = short.rsplit(" - ", 1)[-1] if " - " in short else short
    clock = _clock(status.get("displayClock"))
    if clock in ("", "0:00"):
        return f"End of {period_label}"
    return f"{clock} - {period_label}"


def _leader(competitor: dict[str, Any]) -> dict[str, Any]:
    """Points leader, with his rebounds/assists when he also leads those."""
    by_cat: dict[str, tuple[str, str, int]] = {}
    for cat in competitor.get("leaders") or []:
        top = (cat.get("leaders") or [{}])[0]
        athlete = top.get("athlete") or {}
        if athlete.get("displayName"):
            by_cat[cat.get("name", "")] = (
                str(athlete.get("id", "")),
                athlete["displayName"],
                int(float(top.get("value", 0) or 0)),
            )
    if "points" not in by_cat:
        return {}
    pid, name, pts = by_cat["points"]
    leader: dict[str, Any] = {"name": name, "points": pts}
    for cat, key in (("rebounds", "rebounds"), ("assists", "assists")):
        if cat in by_cat and by_cat[cat][0] == pid:
            leader[key] = by_cat[cat][2]
    return leader


def parse_scoreboard(data: dict[str, Any], game_date: date) -> list[dict[str, Any]]:
    """ESPN scoreboard JSON → the pipeline's normalized game dicts."""
    games: list[dict[str, Any]] = []
    for event in data.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        home_team, away_team = espn_abbr(home.get("team", {})), espn_abbr(away.get("team", {}))
        if not home_team or not away_team:
            logger.warning(f"ESPN: unknown team in event {event.get('id')}: {event.get('name')}")
            continue

        tipoff = None
        with contextlib.suppress(ValueError):
            tipoff = datetime.fromisoformat(str(event.get("date", "")).replace("Z", "+00:00"))

        status = event.get("status") or comp.get("status") or {}
        status_type = status.get("type") or {}
        state = status_type.get("state", "pre")
        game_status = _STATE_TO_STATUS.get(state, 1)

        def periods(c: dict[str, Any]) -> list[dict[str, int]]:
            return [
                {"period": i + 1, "score": int(float(ls.get("value", 0) or 0))}
                for i, ls in enumerate(c.get("linescores") or [])
            ]

        games.append({
            "game_id": f"{game_date.isoformat()}_{away_team}_{home_team}",
            "home_team": home_team,
            "away_team": away_team,
            "tipoff": tipoff,
            "venue": (comp.get("venue") or {}).get("fullName", ""),
            "game_status": game_status,
            "game_status_text": _status_text(state, status, tipoff),
            "period": int(status.get("period", 0) or 0) if game_status > 1 else 0,
            "game_clock": _clock(status.get("displayClock")) if game_status == 2 else "",
            "nba_game_id": "",
            "espn_event_id": str(event.get("id", "")),
            "home_score": int(float(home.get("score", 0) or 0)),
            "away_score": int(float(away.get("score", 0) or 0)),
            "home_periods": periods(home),
            "away_periods": periods(away),
            "home_leader": _leader(home),
            "away_leader": _leader(away),
        })
    return games


def _split_made_attempts(value: str) -> float:
    try:
        made, att = (int(x) for x in value.split("-"))
    except ValueError:
        return 0.0
    return round(made / att, 3) if att else 0.0


def _int(value: str) -> int:
    try:
        return int(str(value).replace("+", ""))
    except ValueError:
        return 0


def parse_boxscore(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """ESPN summary JSON → (home_players, away_players) as LivePlayerStats dicts."""
    home_abbr = away_abbr = None
    for c in ((data.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []:
        if c.get("homeAway") == "home":
            home_abbr = espn_abbr(c.get("team", {}))
        elif c.get("homeAway") == "away":
            away_abbr = espn_abbr(c.get("team", {}))

    home: list[dict[str, Any]] = []
    away: list[dict[str, Any]] = []
    for team_block in (data.get("boxscore") or {}).get("players") or []:
        abbr = espn_abbr(team_block.get("team", {}))
        players: list[dict[str, Any]] = []
        for stat_group in team_block.get("statistics") or []:
            keys = stat_group.get("keys") or []
            for a in stat_group.get("athletes") or []:
                stats = a.get("stats") or []
                if a.get("didNotPlay") or len(stats) != len(keys):
                    continue
                s = dict(zip(keys, stats, strict=True))
                athlete = a.get("athlete") or {}
                players.append({
                    "name": athlete.get("displayName", "Unknown"),
                    "player_id": str(athlete.get("id", "")),
                    "position": (athlete.get("position") or {}).get("abbreviation", ""),
                    "team": abbr or "",
                    "minutes": s.get("minutes", "0") or "0",
                    "points": _int(s.get("points", 0)),
                    "rebounds": _int(s.get("rebounds", 0)),
                    "assists": _int(s.get("assists", 0)),
                    "steals": _int(s.get("steals", 0)),
                    "blocks": _int(s.get("blocks", 0)),
                    "turnovers": _int(s.get("turnovers", 0)),
                    "fouls": _int(s.get("fouls", 0)),
                    "plus_minus": _int(s.get("plusMinus", 0)),
                    "fg_pct": _split_made_attempts(s.get("fieldGoalsMade-fieldGoalsAttempted", "")),
                    "three_pct": _split_made_attempts(
                        s.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "")
                    ),
                    "ft_pct": _split_made_attempts(s.get("freeThrowsMade-freeThrowsAttempted", "")),
                })
        if abbr and abbr == home_abbr:
            home = players
        elif abbr and abbr == away_abbr:
            away = players
    return home, away


class ESPNConnector(BaseConnector):
    """Connector for ESPN's public NBA site API."""

    BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

    def __init__(self) -> None:
        super().__init__(name="ESPN", base_url=self.BASE, timeout=15.0)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "CourtEdge/1.0"},
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        client = await self._get_client()
        try:
            response = await client.get(f"{self.BASE}{endpoint}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"ESPN HTTP error: {e.response.status_code} for {endpoint}")
            raise
        except httpx.TimeoutException:
            logger.error(f"ESPN timeout for {endpoint}")
            raise

    async def health_check(self) -> bool:
        try:
            await self.fetch("/scoreboard")
            return True
        except Exception:
            return False

    async def get_games(self, game_date: date) -> list[dict[str, Any]]:
        """Games on an NBA (US Eastern) date, normalized for the pipeline."""
        data = await self.fetch("/scoreboard", params={"dates": game_date.strftime("%Y%m%d")})
        return parse_scoreboard(data, game_date)

    async def get_boxscore(
        self, event_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        data = await self.fetch("/summary", params={"event": event_id})
        return parse_boxscore(data)

    async def get_roster_names(self, abbr: str) -> list[str]:
        """Current roster player names for a team (NBA abbreviation)."""
        team_id = ABBR_TO_ESPN_TEAM_ID[abbr]
        data = await self.fetch(f"/teams/{team_id}/roster")
        return [a["displayName"] for a in data.get("athletes") or [] if a.get("displayName")]
