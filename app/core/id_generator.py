from datetime import datetime, timezone
import os
import threading
import time


SNOWFLAKE_EPOCH_MS = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
WORKER_ID_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1


class SnowflakeIdGenerator:
    def __init__(self, worker_id: int | None = None) -> None:
        self.worker_id = self._normalize_worker_id(worker_id)
        self._lock = threading.Lock()
        self._last_timestamp = -1
        self._sequence = 0

    def generate(self) -> str:
        with self._lock:
            timestamp = self._current_timestamp_ms()
            if timestamp < self._last_timestamp:
                timestamp = self._last_timestamp

            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp = self._wait_next_millis(timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp
            value = (
                ((timestamp - SNOWFLAKE_EPOCH_MS) << (WORKER_ID_BITS + SEQUENCE_BITS))
                | (self.worker_id << SEQUENCE_BITS)
                | self._sequence
            )
            return str(value)

    def _normalize_worker_id(self, worker_id: int | None) -> int:
        if worker_id is None:
            raw_value = os.getenv("SNOWFLAKE_WORKER_ID", "1")
            try:
                worker_id = int(raw_value)
            except ValueError:
                worker_id = 1
        return worker_id & MAX_WORKER_ID

    def _current_timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, timestamp: int) -> int:
        current = self._current_timestamp_ms()
        while current <= timestamp:
            current = self._current_timestamp_ms()
        return current


id_generator = SnowflakeIdGenerator()


def generate_file_id() -> str:
    return id_generator.generate()
