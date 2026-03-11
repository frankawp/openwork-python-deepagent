from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Iterator, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

from .db import SessionLocal


class MySQLSaver(BaseCheckpointSaver[str]):
    """MySQL checkpointer using checkpoints/writes tables."""

    def _get_session(self) -> Session:
        return SessionLocal()

    def _pack(self, value: Any) -> str:
        type_tag, data = self.serde.dumps_typed(value)
        payload = {"type": type_tag, "data": base64.b64encode(data).decode("utf-8")}
        return json.dumps(payload)

    def _unpack(self, raw: str) -> Any:
        payload = json.loads(raw)
        data = base64.b64decode(payload["data"])
        return self.serde.loads_typed((payload["type"], data))

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        with self._get_session() as db:
            if checkpoint_id:
                row = db.execute(
                    text(
                        """
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint, metadata
                        FROM checkpoints
                        WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                          AND checkpoint_id = :checkpoint_id
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    },
                ).fetchone()
            else:
                row = db.execute(
                    text(
                        """
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint, metadata
                        FROM checkpoints
                        WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                        ORDER BY checkpoint_id DESC
                        LIMIT 1
                        """
                    ),
                    {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
                ).fetchone()

            if not row:
                return None

            checkpoint_id, parent_checkpoint_id, checkpoint_blob, metadata_blob = row
            checkpoint = self._unpack(checkpoint_blob)
            metadata = self._unpack(metadata_blob)

            writes_rows = db.execute(
                text(
                    """
                    SELECT task_id, channel, value
                    FROM writes
                    WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                      AND checkpoint_id = :checkpoint_id
                    ORDER BY idx ASC
                    """
                ),
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                },
            ).fetchall()

            pending_writes = [
                (task_id, channel, self._unpack(value)) for task_id, channel, value in writes_rows
            ]

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
                pending_writes=pending_writes,
            )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if not config:
            return iter([])

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        before_id = get_checkpoint_id(before) if before else None

        query = """
            SELECT checkpoint_id, parent_checkpoint_id, checkpoint, metadata
            FROM checkpoints
            WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
        """
        params: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
        if before_id:
            query += " AND checkpoint_id < :before_id"
            params["before_id"] = before_id
        query += " ORDER BY checkpoint_id DESC"
        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        with self._get_session() as db:
            rows = db.execute(text(query), params).fetchall()
            for checkpoint_id, parent_checkpoint_id, checkpoint_blob, metadata_blob in rows:
                checkpoint = self._unpack(checkpoint_blob)
                metadata = self._unpack(metadata_blob)

                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_id,
                        }
                    },
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=(
                        {
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": checkpoint_ns,
                                "checkpoint_id": parent_checkpoint_id,
                            }
                        }
                        if parent_checkpoint_id
                        else None
                    ),
                )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        checkpoint_blob = self._pack(checkpoint)
        metadata_blob = self._pack(get_checkpoint_metadata(config, metadata))

        with self._get_session() as db:
            db.execute(
                text(
                    """
                    INSERT INTO checkpoints
                      (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                    VALUES
                      (:thread_id, :checkpoint_ns, :checkpoint_id, :parent_checkpoint_id, NULL, :checkpoint, :metadata)
                    ON DUPLICATE KEY UPDATE
                      parent_checkpoint_id = VALUES(parent_checkpoint_id),
                      checkpoint = VALUES(checkpoint),
                      metadata = VALUES(metadata)
                    """
                ),
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint["id"],
                    "parent_checkpoint_id": parent_checkpoint_id,
                    "checkpoint": checkpoint_blob,
                    "metadata": metadata_blob,
                },
            )
            db.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        with self._get_session() as db:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                payload = {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "idx": write_idx,
                    "channel": channel,
                    "type": None,
                    "value": self._pack(value),
                }
                if write_idx >= 0:
                    db.execute(
                        text(
                            """
                            INSERT IGNORE INTO writes
                              (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value)
                            VALUES
                              (:thread_id, :checkpoint_ns, :checkpoint_id, :task_id, :idx, :channel, :type, :value)
                            """
                        ),
                        payload,
                    )
                else:
                    db.execute(
                        text(
                            """
                            INSERT INTO writes
                              (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value)
                            VALUES
                              (:thread_id, :checkpoint_ns, :checkpoint_id, :task_id, :idx, :channel, :type, :value)
                            ON DUPLICATE KEY UPDATE
                              channel = VALUES(channel),
                              type = VALUES(type),
                              value = VALUES(value)
                            """
                        ),
                        payload,
                    )
            db.commit()

    def delete_thread(self, thread_id: str) -> None:
        with self._get_session() as db:
            db.execute(text("DELETE FROM writes WHERE thread_id = :thread_id"), {"thread_id": thread_id})
            db.execute(
                text("DELETE FROM checkpoints WHERE thread_id = :thread_id"),
                {"thread_id": thread_id},
            )
            db.commit()

    def clear_channel_value(self, thread_id: str, channel: str, checkpoint_ns: str = "") -> int:
        """Remove a channel from persisted checkpoint channel_values for a thread.

        This preserves conversation history while forcing middleware that caches
        private state (e.g., skills metadata) to recompute on next run.
        """
        updated = 0
        with self._get_session() as db:
            rows = db.execute(
                text(
                    """
                    SELECT checkpoint_id, checkpoint
                    FROM checkpoints
                    WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                    """
                ),
                {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
            ).fetchall()

            for checkpoint_id, checkpoint_blob in rows:
                checkpoint = self._unpack(checkpoint_blob)
                if not isinstance(checkpoint, dict):
                    continue
                channel_values = checkpoint.get("channel_values")
                if not isinstance(channel_values, dict) or channel not in channel_values:
                    continue

                updated_channel_values = dict(channel_values)
                updated_channel_values.pop(channel, None)
                checkpoint["channel_values"] = updated_channel_values

                db.execute(
                    text(
                        """
                        UPDATE checkpoints
                        SET checkpoint = :checkpoint
                        WHERE thread_id = :thread_id
                          AND checkpoint_ns = :checkpoint_ns
                          AND checkpoint_id = :checkpoint_id
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "checkpoint": self._pack(checkpoint),
                    },
                )
                updated += 1

            if updated:
                db.commit()
        return updated

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ):
        return await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit)))

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)
