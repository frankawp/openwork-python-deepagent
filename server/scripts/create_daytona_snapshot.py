#!/usr/bin/env python3
"""
Create a Daytona snapshot with preinstalled MCP runtime dependencies.

This script prepares a snapshot so Openwork sandboxes do not need to install
tools during runtime initialization.

Usage examples:

  server/.venv/bin/python server/scripts/create_daytona_snapshot.py \
    --name openwork-mcp-core-us

  server/.venv/bin/python server/scripts/create_daytona_snapshot.py \
    --name openwork-mcp-core-us \
    --region us \
    --verify
"""

from __future__ import annotations

import argparse
import base64
import textwrap
import os
import sys
from pathlib import Path
from typing import Any


def _bootstrap_import_path() -> None:
    server_dir = Path(__file__).resolve().parents[1]
    os.chdir(server_dir)
    server_dir_str = str(server_dir)
    if server_dir_str not in sys.path:
        sys.path.insert(0, server_dir_str)


_bootstrap_import_path()

from daytona import CreateSandboxFromSnapshotParams, Daytona  # noqa: E402
from daytona.common.image import Image  # noqa: E402
from daytona.common.snapshot import CreateSnapshotParams  # noqa: E402


def _ensure_ssl_cert_file_env() -> None:
    # Keep TLS verification enabled while ensuring urllib3 can find CA roots.
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except Exception:
        return

    ca_bundle = certifi.where()
    if not ca_bundle:
        return
    os.environ["SSL_CERT_FILE"] = ca_bundle
    if not os.environ.get("REQUESTS_CA_BUNDLE"):
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Daytona snapshot with preinstalled Openwork MCP runtime "
            "dependencies (node/npm/npx, uv/uvx, supergateway, filesystem/fetch MCP)."
        )
    )
    parser.add_argument("--name", required=True, help="Snapshot name.")
    parser.add_argument(
        "--region",
        default=None,
        help="Target region ID. Defaults to DAYTONA_TARGET from environment.",
    )
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create temporary sandbox from snapshot and verify required binaries.",
    )
    parser.add_argument(
        "--keep-verify-sandbox",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Keep verification sandbox for debugging (default: false).",
    )
    return parser.parse_args()


def _resolve_region_id(explicit_region: str | None) -> str:
    value = (explicit_region or os.environ.get("DAYTONA_TARGET") or "").strip()
    if value:
        return value
    # Default to "us" for local Openwork deployments if not explicitly set.
    return "us"


def _build_image() -> Image:
    # Snapshot baseline: Node 22 + latest fetch MCP compatible with modern jsdom stack.
    fetch_pkg = "mcp-fetch-server@1.1.2"
    readme_content = textwrap.dedent(
        """
        # 欢迎使用 Openwork Agent

        这是你的工作区助手，可以帮你把想法变成可执行结果。

        ## 你可以这样用我

        1. 直接说目标：例如“整理这份数据并给出结论”。
        2. 说清要求：例如“用中文、给我三条建议、结果放在文件里”。
        3. 分步推进：先让我给方案，再执行，再复核结果。

        ## 我现在能做什么

        - 帮你读写工作区里的文件。
        - 帮你整理信息、分析数据、生成文档。
        - 使用你启用的“技能”来按固定方法完成任务。
        - 使用你配置的外部连接（例如数据库、网页服务）获取信息并处理。

        ## 我的边界（重要）

        - 我只能访问被允许的工作区内容。
        - 我不会自动拥有外部系统权限，必须由你先配置账号信息。
        - 没有启用的技能或外部连接，我不会假装能用。
        - 当外部连接异常时，我会继续完成可做的部分，并提示你哪里受影响。

        ## 建议的开场方式

        你可以先发一句：
        “请先告诉我你会怎么做，再开始执行。”
        """
    ).strip()
    encoded_readme = base64.b64encode(readme_content.encode("utf-8")).decode("ascii")
    commands = [
        "apt-get update",
        (
            "apt-get install -y --no-install-recommends "
            "curl ca-certificates gnupg git"
        ),
        "mkdir -p /etc/apt/keyrings",
        (
            "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key "
            "| gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg"
        ),
        (
            "echo 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] "
            "https://deb.nodesource.com/node_22.x nodistro main' "
            "> /etc/apt/sources.list.d/nodesource.list"
        ),
        "apt-get update",
        "apt-get install -y --no-install-recommends nodejs",
        "rm -rf /var/lib/apt/lists/*",
        "python -m pip install --no-cache-dir --upgrade pip",
        "python -m pip install --no-cache-dir uv",
        "npm config set fund false",
        "npm config set update-notifier false",
        f"npm install -g supergateway @modelcontextprotocol/server-filesystem {fetch_pkg}",
        "mkdir -p /home/daytona",
        (
            "python -c \"import base64,pathlib; "
            "pathlib.Path('/home/daytona/readme.md').write_bytes("
            f"base64.b64decode('{encoded_readme}'))\""
        ),
    ]
    commands.append("python -m pip install --no-cache-dir mcp-server-starrocks")
    return Image.debian_slim("3.12").run_commands(*commands).workdir("/home/daytona")


def _snapshot_logs(line: str) -> None:
    print(line, flush=True)


def _verify_snapshot(
    *,
    daytona: Daytona,
    snapshot_id: str,
    keep_verify_sandbox: bool,
) -> None:
    verify_labels = {
        "openwork_app": "openwork",
        "openwork_snapshot_verify": "true",
    }
    sandbox = daytona.create(
        params=CreateSandboxFromSnapshotParams(
            language="python",
            snapshot=snapshot_id,
            labels=verify_labels,
            ephemeral=True,
        ),
        timeout=180,
    )
    should_delete = not keep_verify_sandbox

    commands = [
        "node",
        "npm",
        "npx",
        "uv",
        "uvx",
        "supergateway",
        "mcp-server-filesystem",
        "mcp-fetch-server",
    ]

    check_lines = [
        "set -eu",
        "missing=0",
    ]
    for command in commands:
        check_lines.append(
            f'if command -v "{command}" >/dev/null 2>&1; then '
            f'echo "OK {command}:$(command -v {command})"; '
            f'else echo "MISSING {command}"; missing=1; fi'
        )
    check_lines.append(
        'if [ -f "/home/daytona/readme.md" ]; then '
        'echo "OK readme.md:/home/daytona/readme.md"; '
        'else echo "MISSING readme.md:/home/daytona/readme.md"; missing=1; fi'
    )
    check_lines.append('node_major="$(node -p \'process.versions.node.split(".")[0]\')"')
    check_lines.append(
        'if [ "${node_major:-0}" -ge 22 ]; then echo "OK node_major:$node_major"; '
        'else echo "MISSING node_major>=22 (actual:${node_major:-unknown})"; missing=1; fi'
    )
    check_lines.append(
        'if python -m pip show "mcp-server-starrocks" >/dev/null 2>&1; then '
        'echo "OK mcp-server-starrocks:installed"; '
        'else echo "MISSING mcp-server-starrocks"; missing=1; fi'
    )
    check_lines.append("exit $missing")
    check_script = "\n".join(check_lines)

    try:
        result = sandbox.process.exec(check_script, timeout=120)
        exit_code = getattr(result, "exit_code", 1)
        output = str(getattr(result, "result", "") or "")
        if exit_code != 0:
            raise RuntimeError(
                "Snapshot verification failed. Missing required binaries.\n"
                f"output:\n{output}"
            )
        print("Verification passed:")
        print(output)
    finally:
        if should_delete:
            try:
                sandbox.delete(timeout=120)
            except Exception as e:
                print(f"Warning: failed to delete verification sandbox {sandbox.id}: {e}")
        else:
            print(f"Verification sandbox kept for debugging: {sandbox.id}")


def _create_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    _ensure_ssl_cert_file_env()
    region_id = _resolve_region_id(args.region)
    os.environ["DAYTONA_TARGET"] = region_id
    daytona = Daytona()
    image = _build_image()
    params = CreateSnapshotParams(
        name=args.name,
        image=image,
        region_id=region_id,
    )
    snapshot = daytona.snapshot.create(
        params,
        on_logs=_snapshot_logs,
    )
    return {
        "snapshot": snapshot,
        "daytona": daytona,
        "region_id": region_id,
    }


def main() -> int:
    args = _parse_args()

    result = _create_snapshot(args)
    snapshot = result["snapshot"]
    daytona = result["daytona"]
    resolved_region = str(result["region_id"])

    snapshot_id = str(getattr(snapshot, "id"))
    snapshot_name = str(getattr(snapshot, "name"))
    snapshot_state = str(getattr(snapshot, "state"))
    snapshot_region = getattr(snapshot, "region_id", None)

    print("\nSnapshot created successfully:")
    print(f"  id: {snapshot_id}")
    print(f"  name: {snapshot_name}")
    print(f"  state: {snapshot_state}")
    print(f"  region: {snapshot_region}")
    if not snapshot_region:
        print(f"  resolved_target: {resolved_region}")

    if args.verify:
        print("\nRunning verification sandbox checks...")
        try:
            _verify_snapshot(
                daytona=daytona,
                snapshot_id=snapshot_id,
                keep_verify_sandbox=args.keep_verify_sandbox,
            )
        except Exception as e:
            message = str(e)
            if "No available runners" in message:
                raise RuntimeError(
                    "Snapshot verification failed because Daytona has no available runners "
                    f"in target region '{resolved_region}'. "
                    "Try another region via --region, or ensure runner capacity is available."
                ) from e
            raise

    print("\nUse this environment variable in Openwork server process:")
    print(f"  export DAYTONA_SNAPSHOT={snapshot_id}")
    print("\nOptional (pin by name instead of id):")
    print(f"  export DAYTONA_SNAPSHOT={snapshot_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
