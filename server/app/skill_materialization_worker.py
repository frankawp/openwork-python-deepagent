from __future__ import annotations

import asyncio
import logging

from .db import SessionLocal
from .skills_service import (
    build_materialization_file_payload,
    claim_next_dirty_thread,
    finalize_materialization_failure,
    finalize_materialization_success,
    mark_materialization_dirty_if_needed,
    materialize_thread_skills,
)

logger = logging.getLogger(__name__)


class SkillMaterializationWorker:
    def __init__(self, poll_interval_seconds: float = 1.5) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="skill-materialization-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await asyncio.to_thread(self._process_one)
            except Exception:
                logger.exception("Skill materialization worker loop failed")
                processed = False

            if not processed:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass

    def _process_one(self) -> bool:
        db = SessionLocal()
        claim = None
        try:
            with db.begin():
                claim = claim_next_dirty_thread(db)
            if not claim:
                return False

            with db.begin():
                _, files = build_materialization_file_payload(
                    db,
                    thread_id=claim.thread_id,
                    desired_hash=claim.desired_hash,
                )

            materialized_root = materialize_thread_skills(
                thread_id=claim.thread_id,
                desired_hash=claim.desired_hash,
                files=files,
            )

            with db.begin():
                finalize_materialization_success(
                    db,
                    thread_id=claim.thread_id,
                    desired_hash=claim.desired_hash,
                    materialized_root=materialized_root,
                )
            return True
        except ValueError as e:
            if claim:
                logger.info("Skipping outdated skill materialization for thread %s: %s", claim.thread_id, e)
                with db.begin():
                    mark_materialization_dirty_if_needed(db, thread_id=claim.thread_id)
            return True
        except Exception as e:
            logger.exception("Skill materialization failed")
            if claim:
                with db.begin():
                    finalize_materialization_failure(
                        db,
                        thread_id=claim.thread_id,
                        error=str(e),
                    )
            return True
        finally:
            db.close()
