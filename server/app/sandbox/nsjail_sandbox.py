from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from ..config import SandboxConfig
from .types import ExecuteResult


class NsjailSandbox:
    def __init__(self, workspace_root: str, config: SandboxConfig) -> None:
        self.workspace_root = Path(workspace_root)
        self.config = config

        if platform.system() != "Linux":
            raise RuntimeError("nsjail sandbox requires Linux")

        nsjail_path = shutil.which(config.nsjail_path) or config.nsjail_path
        if not Path(nsjail_path).exists():
            raise RuntimeError(f"nsjail not found at '{config.nsjail_path}'")

        self.nsjail_path = nsjail_path
        self.rootfs_path = self.workspace_root / config.rootfs_dir
        self._ensure_rootfs()

    def _ensure_rootfs(self) -> None:
        rootfs = self.rootfs_path
        (rootfs / "workspace").mkdir(parents=True, exist_ok=True)
        (rootfs / "tmp").mkdir(parents=True, exist_ok=True)

        for mount in self.config.readonly_bind_mounts:
            if not mount.startswith("/"):
                continue
            target = rootfs / mount.lstrip("/")
            target.mkdir(parents=True, exist_ok=True)

        if self.config.mount_dev:
            (rootfs / "dev").mkdir(parents=True, exist_ok=True)
        if self.config.mount_proc:
            (rootfs / "proc").mkdir(parents=True, exist_ok=True)

    def _build_args(
        self,
        command: str,
        env: dict[str, str],
        timeout_seconds: int,
        *,
        with_seccomp: bool = True,
    ) -> list[str]:
        use_shared_mount_ns = self.config.disable_clone_newns
        chroot_path = "/" if use_shared_mount_ns else str(self.rootfs_path)
        cwd_path = str(self.workspace_root) if use_shared_mount_ns else "/workspace"

        args: list[str] = [
            self.nsjail_path,
            "--quiet",
            "--mode",
            "o",
            "--user",
            str(os.getuid()),
            "--group",
            str(os.getgid()),
            "--chroot",
            chroot_path,
            "--cwd",
            cwd_path,
            "--time_limit",
            str(timeout_seconds),
            "--rlimit_cpu",
            str(self.config.rlimit_cpu_sec),
            "--rlimit_as",
            str(self.config.rlimit_as_mb * 1024 * 1024),
            "--rlimit_fsize",
            str(self.config.rlimit_fsize_mb * 1024 * 1024),
        ]

        if self.config.disable_clone_newns:
            args.append("--disable_clone_newns")
        else:
            for mount in self.config.readonly_bind_mounts:
                if not mount.startswith("/"):
                    continue
                if not Path(mount).exists():
                    continue
                args.extend(["--bindmount_ro", f"{mount}:{mount}"])

            if self.config.mount_dev and Path("/dev").exists():
                args.extend(["--bindmount", "/dev:/dev"])

            if self.config.mount_proc and Path("/proc").exists():
                args.extend(["--bindmount", "/proc:/proc"])

            args.extend(["--bindmount", f"{self.workspace_root}:/workspace"])

        if with_seccomp and self.config.seccomp:
            args.extend(["--seccomp_string", self.config.seccomp])

        for key, value in env.items():
            args.extend(["--env", f"{key}={value}"])

        args.extend(["--", "/bin/sh", "-c", command])
        return args

    @staticmethod
    def _is_seccomp_compile_error(stderr: str) -> bool:
        lowered = stderr.lower()
        return "could not compile policy" in lowered or "couldn't prepare sandboxing policy" in lowered

    @staticmethod
    def _is_mount_permission_error(stderr: str) -> bool:
        lowered = stderr.lower()
        return "operation not permitted" in lowered and "buildmounttree" in lowered

    def run(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
        max_output_bytes: int | None = None,
    ) -> ExecuteResult:
        if not command or not isinstance(command, str):
            return ExecuteResult(
                output="Error: Shell tool expects a non-empty command string.",
                exit_code=1,
                truncated=False,
            )

        timeout = timeout_seconds or self.config.time_limit_sec
        output_limit = max_output_bytes or self.config.max_output_bytes

        base_env = dict(env or {})
        if "HOME" not in base_env:
            base_env["HOME"] = "/tmp"
        if "LANG" not in base_env:
            base_env["LANG"] = "C.UTF-8"
        if "PATH" not in base_env:
            base_env["PATH"] = os.environ.get("PATH", "")

        args = self._build_args(command, base_env, timeout, with_seccomp=True)

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResult(
                output=f"Error: Command timed out after {timeout} seconds.",
                exit_code=None,
                truncated=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ExecuteResult(
                output=f"Error: Failed to run command. {exc}",
                exit_code=1,
                truncated=False,
            )

        seccomp_fallback_used = False
        if proc.returncode != 0 and self._is_seccomp_compile_error(proc.stderr or ""):
            seccomp_fallback_used = True
            args_without_seccomp = self._build_args(
                command,
                base_env,
                timeout,
                with_seccomp=False,
            )
            try:
                proc = subprocess.run(
                    args_without_seccomp,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return ExecuteResult(
                    output=f"Error: Command timed out after {timeout} seconds.",
                    exit_code=None,
                    truncated=False,
                )
            except Exception as exc:  # pragma: no cover - defensive
                return ExecuteResult(
                    output=f"Error: Failed to run command. {exc}",
                    exit_code=1,
                    truncated=False,
                )

        output = ""
        if seccomp_fallback_used:
            output += "[stderr] Warning: seccomp policy compile failed; retried without seccomp.\n"
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            for line in proc.stderr.splitlines():
                output += f"[stderr] {line}\n"

        if proc.returncode != 0 and self._is_mount_permission_error(proc.stderr or ""):
            output = (
                "Error: nsjail is installed but cannot create mount namespaces in this runtime "
                "(Operation not permitted).\n"
                "This usually happens in unprivileged containers.\n"
                "Fix options:\n"
                "1) Run the server with container privileges/capabilities required by nsjail.\n"
                "2) Set 'sandbox.allow_local_fallback: true' in config.yaml to use LocalSandbox.\n\n"
            ) + output

        if not output.strip():
            output = "<no output>"

        truncated = False
        if len(output) > output_limit:
            output = output[:output_limit] + "\n\n... Output truncated."
            truncated = True

        return ExecuteResult(
            output=output,
            exit_code=proc.returncode,
            truncated=truncated,
        )
