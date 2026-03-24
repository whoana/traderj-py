"""TunerStore — DB operations for tuning_history and tuning_report tables.

Wraps the existing DataStore's internal DB connection.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from engine.tuner.enums import (
    DiagnosisDirection,
    LLMConfidence,
    LLMProviderName,
    TierLevel,
    TuningStatus,
)
from engine.tuner.models import (
    EvalMetrics,
    ParameterChange,
    TuningHistoryRecord,
    TuningReport,
)

logger = logging.getLogger(__name__)


class TunerStore:
    """DB access layer for tuning tables."""

    def __init__(self, data_store: object) -> None:
        self._store = data_store
        # Detect backend type
        self._is_postgres = hasattr(data_store, "pool")

    # ── Internal DB access ──

    async def _execute(self, sql: str, params: tuple | list = ()) -> None:
        if self._is_postgres:
            async with self._store.pool.acquire() as conn:  # type: ignore[union-attr]
                await conn.execute(sql, *params)
        else:
            await self._store.db.execute(sql, params)  # type: ignore[union-attr]
            await self._store.db.commit()  # type: ignore[union-attr]

    async def _fetch_all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        if self._is_postgres:
            async with self._store.pool.acquire() as conn:  # type: ignore[union-attr]
                rows = await conn.fetch(sql, *params)
                return [dict(r) for r in rows]
        else:
            cursor = await self._store.db.execute(sql, params)  # type: ignore[union-attr]
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def _fetch_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        if self._is_postgres:
            async with self._store.pool.acquire() as conn:  # type: ignore[union-attr]
                row = await conn.fetchrow(sql, *params)
                return dict(row) if row else None
        else:
            cursor = await self._store.db.execute(sql, params)  # type: ignore[union-attr]
            row = await cursor.fetchone()
            return dict(row) if row else None

    # ── Tuning History ──

    async def save_tuning_history(self, record: TuningHistoryRecord) -> None:
        """Save each ParameterChange as an individual row with the same tuning_id."""
        for change in record.changes:
            sql = """
                INSERT INTO tuning_history (
                    tuning_id, created_at, strategy_id, tier, parameter_name,
                    old_value, new_value, change_pct, reason, eval_window,
                    eval_pf, eval_mdd, eval_winrate,
                    validation_pf, validation_mdd,
                    llm_provider, llm_model, llm_diagnosis, llm_confidence,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                record.tuning_id,
                record.created_at.isoformat(),
                record.strategy_id,
                change.tier.value,
                change.parameter_name,
                change.old_value,
                change.new_value,
                change.change_pct,
                record.reason,
                record.eval_metrics.eval_window,
                record.eval_metrics.profit_factor,
                record.eval_metrics.max_drawdown,
                record.eval_metrics.win_rate,
                record.validation_pf,
                record.validation_mdd,
                record.llm_provider.value if record.llm_provider else None,
                record.llm_model,
                record.llm_diagnosis,
                record.llm_confidence.value if record.llm_confidence else None,
                record.status.value,
            )

            if self._is_postgres:
                sql = self._to_pg_placeholders(sql)

            await self._execute(sql, params)

        logger.info(
            "Saved tuning history: %s (%d changes) for %s",
            record.tuning_id,
            len(record.changes),
            record.strategy_id,
        )

    async def save_tuning_report(self, report: TuningReport) -> None:
        """Save tuning evaluation report."""
        sql = """
            INSERT INTO tuning_report (
                tuning_id, created_at, eval_window, strategy_id, regime,
                total_trades, win_rate, profit_factor, max_drawdown,
                avg_r_multiple, signal_accuracy, recommendations, applied_changes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        recs_json = json.dumps(
            [{"name": r.name, "direction": r.direction.value, "reason": r.reason} for r in report.recommendations]
        )
        changes_json = json.dumps(
            [
                {
                    "name": c.parameter_name,
                    "tier": c.tier.value,
                    "old": c.old_value,
                    "new": c.new_value,
                    "change_pct": c.change_pct,
                }
                for c in report.applied_changes
            ]
        )
        params = (
            report.tuning_id,
            report.created_at.isoformat(),
            report.eval_window,
            report.strategy_id,
            report.metrics.regime,
            report.metrics.total_trades,
            report.metrics.win_rate,
            report.metrics.profit_factor,
            report.metrics.max_drawdown,
            report.metrics.avg_r_multiple,
            report.metrics.signal_accuracy,
            recs_json,
            changes_json,
        )

        if self._is_postgres:
            sql = self._to_pg_placeholders(sql)

        await self._execute(sql, params)

    async def get_tuning_history(
        self,
        strategy_id: str | None = None,
        status: TuningStatus | None = None,
        limit: int = 50,
    ) -> list[TuningHistoryRecord]:
        """Query tuning history, grouped by tuning_id."""
        conditions = []
        params: list = []

        if strategy_id:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT * FROM tuning_history
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        if self._is_postgres:
            sql = self._to_pg_placeholders(sql)

        rows = await self._fetch_all(sql, tuple(params))
        return self._rows_to_records(rows)

    async def get_latest_tuning(self, strategy_id: str) -> TuningHistoryRecord | None:
        """Get the most recent tuning record for a strategy."""
        records = await self.get_tuning_history(strategy_id=strategy_id, limit=1)
        return records[0] if records else None

    async def update_tuning_status(
        self,
        tuning_id: str,
        status: TuningStatus,
        rollback_at: datetime | None = None,
    ) -> None:
        """Update status for all rows with the given tuning_id."""
        if rollback_at:
            sql = "UPDATE tuning_history SET status = ?, rollback_at = ? WHERE tuning_id = ?"
            params = (status.value, rollback_at.isoformat(), tuning_id)
        else:
            sql = "UPDATE tuning_history SET status = ? WHERE tuning_id = ?"
            params = (status.value, tuning_id)

        if self._is_postgres:
            sql = self._to_pg_placeholders(sql)

        await self._execute(sql, params)
        logger.info("Updated tuning %s status to %s", tuning_id, status.value)

    async def get_last_change_direction(
        self,
        strategy_id: str,
        parameter_name: str,
    ) -> DiagnosisDirection | None:
        """Get the direction of the most recent change for a parameter (Tier 2 check)."""
        sql = """
            SELECT old_value, new_value FROM tuning_history
            WHERE strategy_id = ? AND parameter_name = ? AND status != 'rejected'
            ORDER BY created_at DESC LIMIT 1
        """
        if self._is_postgres:
            sql = self._to_pg_placeholders(sql)

        row = await self._fetch_one(sql, (strategy_id, parameter_name))
        if not row:
            return None

        if row["new_value"] > row["old_value"]:
            return DiagnosisDirection.INCREASE
        return DiagnosisDirection.DECREASE

    async def count_consecutive_rollbacks(self, strategy_id: str) -> int:
        """Count most recent consecutive rolled_back statuses."""
        sql = """
            SELECT DISTINCT tuning_id, status, created_at FROM tuning_history
            WHERE strategy_id = ?
            ORDER BY created_at DESC, tuning_id DESC
        """
        if self._is_postgres:
            sql = self._to_pg_placeholders(sql)

        rows = await self._fetch_all(sql, (strategy_id,))
        count = 0
        seen_ids: set[str] = set()
        for row in rows:
            tid = row["tuning_id"]
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            if row["status"] == TuningStatus.ROLLED_BACK.value:
                count += 1
            else:
                break
        return count

    async def get_monitoring_sessions(self) -> list[TuningHistoryRecord]:
        """Return all records with status='monitoring'."""
        return await self.get_tuning_history(status=TuningStatus.MONITORING, limit=100)

    # ── Helpers ──

    def _rows_to_records(self, rows: list[dict]) -> list[TuningHistoryRecord]:
        """Group rows by tuning_id into TuningHistoryRecord objects."""
        groups: dict[str, list[dict]] = {}
        for row in rows:
            tid = row["tuning_id"]
            if tid not in groups:
                groups[tid] = []
            groups[tid].append(row)

        records = []
        for tid, group_rows in groups.items():
            first = group_rows[0]
            changes = [
                ParameterChange(
                    parameter_name=r["parameter_name"],
                    tier=TierLevel(r["tier"]),
                    old_value=r["old_value"],
                    new_value=r["new_value"],
                    change_pct=r["change_pct"],
                )
                for r in group_rows
            ]
            records.append(
                TuningHistoryRecord(
                    tuning_id=tid,
                    created_at=datetime.fromisoformat(first["created_at"]),
                    strategy_id=first["strategy_id"],
                    changes=changes,
                    eval_metrics=EvalMetrics(
                        strategy_id=first["strategy_id"],
                        eval_window=first["eval_window"],
                        regime=None,
                        total_trades=0,
                        win_rate=first.get("eval_winrate") or 0.0,
                        profit_factor=first.get("eval_pf") or 0.0,
                        max_drawdown=first.get("eval_mdd") or 0.0,
                        avg_r_multiple=0.0,
                        signal_accuracy=0.0,
                        avg_holding_hours=0.0,
                        total_return_pct=0.0,
                        sharpe_ratio=0.0,
                    ),
                    validation_pf=first.get("validation_pf"),
                    validation_mdd=first.get("validation_mdd"),
                    llm_provider=LLMProviderName(first["llm_provider"]) if first.get("llm_provider") else LLMProviderName.DEGRADED,
                    llm_model=first.get("llm_model"),
                    llm_diagnosis=first.get("llm_diagnosis"),
                    llm_confidence=LLMConfidence(first["llm_confidence"]) if first.get("llm_confidence") else None,
                    reason=first["reason"],
                    status=TuningStatus(first["status"]),
                )
            )
        return records

    @staticmethod
    def _to_pg_placeholders(sql: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL $1, $2, ..."""
        parts = sql.split("?")
        result = parts[0]
        for i, part in enumerate(parts[1:], 1):
            result += f"${i}" + part
        return result
