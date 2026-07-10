"""
telemetry/telemetry_store.py
=============================
Append-only JSONL telemetry store for the AMD Hackathon orchestration framework.

Every pipeline execution appends a single JSON line to a JSONL file.
This design is:
- Thread-safe (uses a file lock per write)
- ML-friendly (JSONL is directly ingestible by pandas, Spark, HF datasets)
- Zero-dependency (no database, no external service)
- Fault-tolerant (corrupt lines can be skipped on read)

The store also maintains an in-memory rolling success rate per model,
which the Routing Engine reads for the history_factor utility component.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Iterator, List, Optional

from telemetry.execution_record import ExecutionRecord

logger = logging.getLogger(__name__)


class TelemetryStore:
    """
    Append-only JSONL telemetry store with in-memory rolling metrics.

    Responsibilities:
    - Append ExecutionRecord objects to a JSONL file atomically.
    - Maintain a per-model rolling success window for the Routing Engine.
    - Expose query helpers for testing and analysis.

    Thread safety: A threading.Lock guards all file writes and in-memory
    mutations.  Reads from the rolling window are lock-free snapshots.

    Args:
        file_path: Absolute path to the JSONL telemetry file.
            If the file does not exist it is created.  If the directory
            does not exist it is created recursively.
        window_size: Number of recent requests per model to keep for
            rolling success rate computation.  Matches history.window_size
            in routing_config.yaml.
        min_samples: Minimum samples before a real success rate is returned.
            Below this threshold, default_score is returned instead.
        default_score: Success rate assumed when insufficient history exists.
    """

    def __init__(
        self,
        file_path: str,
        window_size: int = 100,
        min_samples: int = 5,
        default_score: float = 0.75,
    ) -> None:
        self._path = Path(file_path)
        self._window_size = window_size
        self._min_samples = min_samples
        self._default_score = default_score
        self._lock = threading.Lock()

        # Rolling deque per model_id: True = success, False = failure
        self._success_window: Dict[str, Deque[bool]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

        self._ensure_file_exists()
        self._replay_from_file()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def append(self, record: ExecutionRecord) -> None:
        """
        Append an ExecutionRecord to the telemetry file and update in-memory
        rolling windows.

        Args:
            record: The execution record to persist.

        Raises:
            IOError: If the file cannot be written.
        """
        line = record.to_json_line()
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                logger.error(
                    "telemetry_write_failed",
                    extra={"request_id": record.request_id, "error": str(exc)},
                )
                raise

            self._update_rolling_window(record)

    def get_model_success_rate(self, model_id: str) -> float:
        """
        Return the rolling success rate for a model.

        Returns default_score if fewer than min_samples are available.

        Args:
            model_id: Fireworks model ID or "local".

        Returns:
            Success rate in [0.0, 1.0].
        """
        window = self._success_window.get(model_id)
        if not window or len(window) < self._min_samples:
            return self._default_score
        return sum(window) / len(window)

    def get_all_success_rates(self) -> Dict[str, float]:
        """
        Return the rolling success rate for every model that has history.

        Returns:
            Dict of model_id → success_rate.
        """
        return {
            model_id: self.get_model_success_rate(model_id)
            for model_id in self._success_window
        }

    def get_recent_records(self, limit: int = 50) -> List[ExecutionRecord]:
        """
        Return up to `limit` most recent records from the JSONL file.

        Lines that fail JSON parsing are skipped with a warning.

        Args:
            limit: Maximum number of records to return (most recent first).

        Returns:
            List of ExecutionRecord objects in reverse chronological order.
        """
        records: List[ExecutionRecord] = []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(ExecutionRecord.from_dict(data))
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("telemetry_corrupt_line", extra={"error": str(exc)})
            if len(records) >= limit:
                break
        return records

    def iter_all_records(self) -> Iterator[ExecutionRecord]:
        """
        Yield every record in the telemetry file in chronological order.

        Corrupt lines are logged and skipped.

        Yields:
            ExecutionRecord objects.
        """
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        yield ExecutionRecord.from_dict(data)
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.warning(
                            "telemetry_corrupt_line", extra={"error": str(exc)}
                        )
        except OSError:
            return

    def record_count(self) -> int:
        """Return the total number of records in the telemetry file."""
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                return sum(1 for line in fh if line.strip())
        except OSError:
            return 0

    def get_file_path(self) -> str:
        """Return the absolute path of the telemetry JSONL file."""
        return str(self._path.resolve())

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _ensure_file_exists(self) -> None:
        """Create the telemetry file (and parent directories) if absent."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()
            logger.info(
                "telemetry_file_created",
                extra={"path": str(self._path)},
            )

    def _replay_from_file(self) -> None:
        """
        Replay existing telemetry records to rebuild in-memory rolling windows.

        Called once during __init__.  Only the last window_size records per
        model are relevant; we iterate the whole file but deque handles trimming.
        """
        replayed = 0
        for record in self.iter_all_records():
            self._update_rolling_window(record)
            replayed += 1
        if replayed:
            logger.info(
                "telemetry_replayed",
                extra={"records": replayed, "path": str(self._path)},
            )

    def _update_rolling_window(self, record: ExecutionRecord) -> None:
        """
        Update the in-memory rolling success window for the model used in record.

        Must be called with self._lock held (or during __init__ before threads start).

        Args:
            record: The execution record to incorporate.
        """
        model_id = record.final_model_id or record.chosen_model_id
        if not model_id:
            return
        success = record.pipeline_succeeded
        self._success_window[model_id].append(success)
