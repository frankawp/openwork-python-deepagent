from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from app.daytona_backend import _create_daytona_sandbox


class _FakeDaytona:
    def __init__(self) -> None:
        self.last_params = None
        self.last_timeout = None

    def create(self, *, params, timeout: int):  # type: ignore[no-untyped-def]
        self.last_params = params
        self.last_timeout = timeout
        return types.SimpleNamespace(id="sbx-1")


class _AcceptAllParams:
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.kwargs = kwargs


class _NoSnapshotParams:
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if "snapshot" in kwargs:
            raise TypeError("snapshot unsupported")
        self.kwargs = kwargs


class _NoLifecycleParams:
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if (
            "auto_stop_interval" in kwargs
            or "auto_archive_interval" in kwargs
            or "auto_delete_interval" in kwargs
        ):
            raise TypeError("lifecycle unsupported")
        self.kwargs = kwargs


class DaytonaSnapshotBindingTests(unittest.TestCase):
    def _fake_cfg(self, *, snapshot: str | None = None):  # type: ignore[no-untyped-def]
        return types.SimpleNamespace(
            sandbox=types.SimpleNamespace(
                daytona_auto_stop_interval_min=0,
                daytona_auto_archive_interval_days=0,
                daytona_auto_delete_interval_days=-1,
            ),
            daytona=types.SimpleNamespace(
                api_key="key",
                api_url="https://example.com/api",
                target="us",
                snapshot=snapshot,
            ),
        )

    def test_create_sandbox_passes_snapshot_when_env_is_set(self) -> None:
        fake_daytona = _FakeDaytona()

        with patch("app.daytona_backend.load_config", return_value=self._fake_cfg(snapshot="snapshot-a")):
            sandbox = _create_daytona_sandbox(
                daytona=fake_daytona,
                create_params_cls=_AcceptAllParams,
                thread_id="thread-1",
            )

        self.assertEqual(sandbox.id, "sbx-1")
        self.assertEqual(fake_daytona.last_timeout, 120)
        self.assertEqual(fake_daytona.last_params.kwargs["snapshot"], "snapshot-a")

    def test_create_sandbox_omits_snapshot_when_env_is_empty(self) -> None:
        fake_daytona = _FakeDaytona()

        with patch("app.daytona_backend.load_config", return_value=self._fake_cfg(snapshot=None)):
            _create_daytona_sandbox(
                daytona=fake_daytona,
                create_params_cls=_AcceptAllParams,
                thread_id="thread-1",
            )

        self.assertNotIn("snapshot", fake_daytona.last_params.kwargs)

    def test_create_sandbox_falls_back_when_snapshot_arg_is_unsupported(self) -> None:
        fake_daytona = _FakeDaytona()

        with patch("app.daytona_backend.load_config", return_value=self._fake_cfg(snapshot="snapshot-a")):
            _create_daytona_sandbox(
                daytona=fake_daytona,
                create_params_cls=_NoSnapshotParams,
                thread_id="thread-1",
            )

        self.assertNotIn("snapshot", fake_daytona.last_params.kwargs)

    def test_create_sandbox_falls_back_when_lifecycle_args_are_unsupported(self) -> None:
        fake_daytona = _FakeDaytona()

        with (
            patch("app.daytona_backend.load_config", return_value=self._fake_cfg()),
            patch.dict("os.environ", {}, clear=False),
        ):
            _create_daytona_sandbox(
                daytona=fake_daytona,
                create_params_cls=_NoLifecycleParams,
                thread_id="thread-1",
            )

        self.assertNotIn("auto_stop_interval", fake_daytona.last_params.kwargs)
        self.assertNotIn("auto_archive_interval", fake_daytona.last_params.kwargs)
        self.assertNotIn("auto_delete_interval", fake_daytona.last_params.kwargs)


if __name__ == "__main__":
    unittest.main()
