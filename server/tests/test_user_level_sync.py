from __future__ import annotations

import datetime as dt
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.mcp_service import sync_user_mcp_bindings
from app.models import (
    MCPServer,
    Skill,
    SkillFile,
    Thread,
    ThreadMCPBinding,
    ThreadMCPRuntimeState,
    ThreadSkillBinding,
    ThreadSkillMaterializationState,
    User,
)
from app.skills_service import content_checksum, sync_user_skill_bindings


class UserLevelSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db: Session = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create_user(self) -> User:
        now = dt.datetime.utcnow()
        user = User(
            username="tester",
            email="tester@example.com",
            password_hash="x",
            is_admin=False,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _create_thread(self, *, user_id: str, title: str, created_at: dt.datetime) -> Thread:
        thread = Thread(
            user_id=user_id,
            status="idle",
            title=title,
            metadata_json={},
            thread_values={},
            created_at=created_at,
            updated_at=created_at,
        )
        self.db.add(thread)
        self.db.flush()
        return thread

    def _create_skill(
        self,
        *,
        user_id: str,
        key: str,
        enabled: bool,
        created_at: dt.datetime,
    ) -> Skill:
        skill = Skill(
            user_id=user_id,
            key=key,
            name=key,
            description=f"desc-{key}",
            enabled=enabled,
            created_at=created_at,
            updated_at=created_at,
        )
        self.db.add(skill)
        self.db.flush()

        content = f"---\nname: {key}\ndescription: desc-{key}\n---\n\n# {key}\n"
        self.db.add(
            SkillFile(
                skill_id=skill.id,
                path="SKILL.md",
                content=content,
                checksum=content_checksum(content),
                updated_at=created_at,
            )
        )
        self.db.flush()
        return skill

    def _create_mcp(
        self,
        *,
        user_id: str,
        key: str,
        enabled: bool,
        created_at: dt.datetime,
    ) -> MCPServer:
        server = MCPServer(
            user_id=user_id,
            key=key,
            name=key,
            description=f"desc-{key}",
            transport="streamable_http",
            config_json={"url": f"http://127.0.0.1/{key}"},
            encrypted_secret_json=None,
            enabled=enabled,
            created_at=created_at,
            updated_at=created_at,
        )
        self.db.add(server)
        self.db.flush()
        return server

    def test_sync_user_skills_rebuilds_all_thread_bindings_and_states(self) -> None:
        user = self._create_user()
        base = dt.datetime(2026, 1, 1, 0, 0, 0)
        t1 = self._create_thread(user_id=user.id, title="t1", created_at=base)
        t2 = self._create_thread(user_id=user.id, title="t2", created_at=base + dt.timedelta(seconds=1))

        s1 = self._create_skill(
            user_id=user.id,
            key="skill-a",
            enabled=True,
            created_at=base + dt.timedelta(seconds=2),
        )
        _ = self._create_skill(
            user_id=user.id,
            key="skill-disabled",
            enabled=False,
            created_at=base + dt.timedelta(seconds=3),
        )
        s2 = self._create_skill(
            user_id=user.id,
            key="skill-b",
            enabled=True,
            created_at=base + dt.timedelta(seconds=4),
        )
        self.db.commit()

        affected = sync_user_skill_bindings(self.db, user_id=user.id)
        self.db.commit()

        self.assertEqual(sorted(affected), sorted([t1.id, t2.id]))

        bindings = (
            self.db.execute(
                select(ThreadSkillBinding)
                .where(ThreadSkillBinding.thread_id.in_([t1.id, t2.id]))
                .order_by(ThreadSkillBinding.thread_id.asc(), ThreadSkillBinding.position.asc())
            )
            .scalars()
            .all()
        )
        self.assertEqual(len(bindings), 4)
        grouped_bindings: dict[str, list[ThreadSkillBinding]] = {}
        for binding in bindings:
            grouped_bindings.setdefault(binding.thread_id, []).append(binding)
        for thread_id in [t1.id, t2.id]:
            chunk = grouped_bindings[thread_id]
            self.assertEqual(len(chunk), 2)
            self.assertEqual(chunk[0].skill_id, s1.id)
            self.assertEqual(chunk[0].position, 0)
            self.assertEqual(chunk[1].skill_id, s2.id)
            self.assertEqual(chunk[1].position, 1)

        states = {
            row.thread_id: row
            for row in self.db.execute(
                select(ThreadSkillMaterializationState).where(
                    ThreadSkillMaterializationState.thread_id.in_([t1.id, t2.id])
                )
            )
            .scalars()
            .all()
        }
        self.assertEqual(states[t1.id].status, "dirty")
        self.assertEqual(states[t2.id].status, "dirty")
        self.assertIsNotNone(states[t1.id].desired_hash)

        for skill in self.db.execute(select(Skill).where(Skill.user_id == user.id)).scalars().all():
            skill.enabled = False

        affected_after_disable = sync_user_skill_bindings(self.db, user_id=user.id)
        self.db.commit()
        self.assertEqual(sorted(affected_after_disable), sorted([t1.id, t2.id]))

        remaining = self.db.execute(select(ThreadSkillBinding)).scalars().all()
        self.assertEqual(remaining, [])

        states_after = {
            row.thread_id: row
            for row in self.db.execute(select(ThreadSkillMaterializationState)).scalars().all()
        }
        self.assertEqual(states_after[t1.id].status, "ready")
        self.assertIsNone(states_after[t1.id].desired_hash)
        self.assertEqual(states_after[t2.id].status, "ready")
        self.assertIsNone(states_after[t2.id].desired_hash)

    def test_sync_user_mcps_rebuilds_all_thread_bindings_and_states(self) -> None:
        user = self._create_user()
        base = dt.datetime(2026, 2, 1, 0, 0, 0)
        t1 = self._create_thread(user_id=user.id, title="t1", created_at=base)
        t2 = self._create_thread(user_id=user.id, title="t2", created_at=base + dt.timedelta(seconds=1))

        m1 = self._create_mcp(
            user_id=user.id,
            key="mcp-a",
            enabled=True,
            created_at=base + dt.timedelta(seconds=2),
        )
        _ = self._create_mcp(
            user_id=user.id,
            key="mcp-disabled",
            enabled=False,
            created_at=base + dt.timedelta(seconds=3),
        )
        m2 = self._create_mcp(
            user_id=user.id,
            key="mcp-b",
            enabled=True,
            created_at=base + dt.timedelta(seconds=4),
        )
        self.db.commit()

        affected = sync_user_mcp_bindings(self.db, user_id=user.id)
        self.db.commit()
        self.assertEqual(sorted(affected), sorted([t1.id, t2.id]))

        bindings = (
            self.db.execute(
                select(ThreadMCPBinding)
                .where(ThreadMCPBinding.thread_id.in_([t1.id, t2.id]))
                .order_by(ThreadMCPBinding.thread_id.asc(), ThreadMCPBinding.position.asc())
            )
            .scalars()
            .all()
        )
        self.assertEqual(len(bindings), 4)
        grouped_bindings: dict[str, list[ThreadMCPBinding]] = {}
        for binding in bindings:
            grouped_bindings.setdefault(binding.thread_id, []).append(binding)
        for thread_id in [t1.id, t2.id]:
            chunk = grouped_bindings[thread_id]
            self.assertEqual(len(chunk), 2)
            self.assertEqual(chunk[0].mcp_id, m1.id)
            self.assertEqual(chunk[0].position, 0)
            self.assertEqual(chunk[1].mcp_id, m2.id)
            self.assertEqual(chunk[1].position, 1)

        states = {
            row.thread_id: row
            for row in self.db.execute(
                select(ThreadMCPRuntimeState).where(ThreadMCPRuntimeState.thread_id.in_([t1.id, t2.id]))
            )
            .scalars()
            .all()
        }
        self.assertEqual(states[t1.id].status, "dirty")
        self.assertEqual(states[t2.id].status, "dirty")

        for server in self.db.execute(select(MCPServer).where(MCPServer.user_id == user.id)).scalars().all():
            server.enabled = False

        affected_after_disable = sync_user_mcp_bindings(self.db, user_id=user.id)
        self.db.commit()
        self.assertEqual(sorted(affected_after_disable), sorted([t1.id, t2.id]))

        remaining = self.db.execute(select(ThreadMCPBinding)).scalars().all()
        self.assertEqual(remaining, [])

        states_after = {
            row.thread_id: row
            for row in self.db.execute(select(ThreadMCPRuntimeState)).scalars().all()
        }
        self.assertEqual(states_after[t1.id].status, "ready")
        self.assertEqual(states_after[t2.id].status, "ready")

    def test_sync_can_target_single_thread_for_new_thread_init(self) -> None:
        user = self._create_user()
        base = dt.datetime(2026, 3, 1, 0, 0, 0)
        t1 = self._create_thread(user_id=user.id, title="t1", created_at=base)
        t2 = self._create_thread(user_id=user.id, title="t2", created_at=base + dt.timedelta(seconds=1))

        self._create_skill(
            user_id=user.id,
            key="skill-a",
            enabled=True,
            created_at=base + dt.timedelta(seconds=2),
        )
        self._create_mcp(
            user_id=user.id,
            key="mcp-a",
            enabled=True,
            created_at=base + dt.timedelta(seconds=3),
        )
        self.db.commit()

        sync_user_skill_bindings(self.db, user_id=user.id, thread_ids=[t1.id])
        sync_user_mcp_bindings(self.db, user_id=user.id, thread_ids=[t1.id])
        self.db.commit()

        t1_skill_count = self.db.execute(
            select(ThreadSkillBinding).where(ThreadSkillBinding.thread_id == t1.id)
        ).scalars().all()
        t2_skill_count = self.db.execute(
            select(ThreadSkillBinding).where(ThreadSkillBinding.thread_id == t2.id)
        ).scalars().all()
        self.assertEqual(len(t1_skill_count), 1)
        self.assertEqual(len(t2_skill_count), 0)

        t1_mcp_count = self.db.execute(
            select(ThreadMCPBinding).where(ThreadMCPBinding.thread_id == t1.id)
        ).scalars().all()
        t2_mcp_count = self.db.execute(
            select(ThreadMCPBinding).where(ThreadMCPBinding.thread_id == t2.id)
        ).scalars().all()
        self.assertEqual(len(t1_mcp_count), 1)
        self.assertEqual(len(t2_mcp_count), 0)


if __name__ == "__main__":
    unittest.main()
