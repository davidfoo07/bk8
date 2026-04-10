"""Market snapshot persistence — save market edges to PostgreSQL.

Called by the pipeline after every run.  Uses upsert logic: only replaces
an existing row if the new snapshot has a HIGHER edge (i.e. we keep the
best pre-game snapshot per game/market, never degrade it).
"""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.database import async_session_factory
from app.models.tables import MarketSnapshot
from app.schemas.game import DailyAnalysis


async def save_market_snapshots(analysis: DailyAnalysis) -> int:
    """Persist all non-empty market edges from a pipeline run.

    Returns the number of rows inserted or updated.
    """
    rows_to_upsert: list[dict] = []

    for game in analysis.games:
        if not game.markets:
            continue

        home = game.home.team
        away = game.away.team
        game_id = f"{analysis.date.isoformat()}_{away}_{home}"

        for mkt_type, mkt in game.markets.items():
            # Skip markets with no Polymarket price (settled / delisted)
            if not mkt.polymarket_home_yes and not mkt.polymarket_home_no:
                continue

            edge = mkt.edge

            rows_to_upsert.append({
                "game_date": analysis.date,
                "game_id": game_id,
                "home_team": home,
                "away_team": away,
                "market_type": mkt_type,
                "home_label": mkt.home_label,
                "away_label": mkt.away_label,
                "line": float(mkt.line) if mkt.line is not None else None,
                "polymarket_home_yes": float(mkt.polymarket_home_yes) if mkt.polymarket_home_yes else None,
                "polymarket_home_no": float(mkt.polymarket_home_no) if mkt.polymarket_home_no else None,
                "model_probability": float(mkt.model_probability) if mkt.model_probability else None,
                "best_side": edge.best_side if edge else None,
                "best_edge": float(edge.best_edge) if edge else None,
                "verdict": edge.verdict if edge else None,
                "kelly_fraction": float(edge.kelly_fraction) if edge else None,
                "yes_ev": float(edge.yes_ev) if edge else None,
                "no_ev": float(edge.no_ev) if edge else None,
            })

    if not rows_to_upsert:
        return 0

    async with async_session_factory() as session:
        async with session.begin():
            count = 0
            for row in rows_to_upsert:
                # Check if existing row has a higher edge — if so, skip
                existing = await session.execute(
                    select(MarketSnapshot.best_edge).where(
                        MarketSnapshot.game_id == row["game_id"],
                        MarketSnapshot.market_type == row["market_type"],
                    )
                )
                existing_edge = existing.scalar()

                if existing_edge is not None:
                    new_edge = row.get("best_edge") or 0
                    if float(existing_edge) >= float(new_edge):
                        # Existing snapshot is better or equal, keep it
                        continue

                # Upsert: insert or replace
                stmt = pg_insert(MarketSnapshot).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["game_id", "market_type"],
                    set_={k: v for k, v in row.items() if k not in ("game_id", "market_type")},
                )
                await session.execute(stmt)
                count += 1

            logger.info(
                f"💾 Saved {count} market snapshots for {analysis.date} "
                f"({len(rows_to_upsert)} candidates, {count} upserted)"
            )
            return count
