"""Prepare selected JSON snapshots in a fresh cache directory and start a local Web process."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from workspace_layout import SOURCE, test_root
from build_core_source import copy_python_sources


async def restore(args: argparse.Namespace, root: Path) -> None:
    if args.memory or args.chat:
        from brain.hc.database.core import get_memory_db
        from memory.message_repository import get_message_store
        from memory.state_api import MemoryState

        try:
            if args.memory:
                snapshot = await MemoryState.from_memory_json_file(args.memory)
                await snapshot.restore_memory(root / "memory")
            if args.chat:
                snapshot = await MemoryState.from_chat_json_file(args.chat)
                await snapshot.restore_chat(root / "memory")
        finally:
            if args.memory:
                await get_memory_db().close()
            if args.chat:
                await get_message_store().close()

    if args.amy:
        from brain.amy.emotional_interface import reset_emotional_interface
        from brain.amy.state_api import AmyState

        try:
            snapshot = await AmyState.from_json_file(args.amy)
            await snapshot.restore(root / "brain" / "amy" / "persistence")
        finally:
            await reset_emotional_interface()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", type=Path, help="Memory snapshot JSON")
    parser.add_argument("--chat", type=Path, help="Message history snapshot JSON")
    parser.add_argument("--amy", type=Path, help="Amy snapshot JSON")
    parser.add_argument("--port", type=int, default=5502)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Restore the selected snapshots and exit")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    frontend = SOURCE / "web_frontend" / "dist"
    if not args.prepare_only and not (frontend / "index.html").is_file():
        parser.error("Build the Web frontend before starting the preset sandbox")

    sandbox = Path(tempfile.mkdtemp(prefix="preset-sandbox-", dir=test_root()))
    source, root = sandbox / "source", sandbox / "data"
    copy_python_sources(source)
    root.mkdir()
    sys.path.insert(0, str(source))
    from config_keys import CONFIG_OVERRIDE_KEYS

    for key in CONFIG_OVERRIDE_KEYS:
        os.environ.pop(key, None)
    os.environ.update(ABYSS_DATA_DIR=str(root), ONEBOT_ENABLED="false", BRIDGE_ENABLED="false",
                      WEB_WS_HOST="127.0.0.1", PYTHONDONTWRITEBYTECODE="1")
    asyncio.run(restore(args, root))
    print(f"Preset data: {root}", flush=True)
    if args.prepare_only:
        return 0
    shutil.copytree(frontend, source / "web_frontend" / "dist")
    entrypoint = source / "scripts" / "web_only.py"
    entrypoint.parent.mkdir()
    shutil.copy2(SOURCE / "scripts" / "web_only.py", entrypoint)
    command = [sys.executable, "-B", str(entrypoint), "--port", str(args.port)]
    if args.no_browser:
        command.append("--no-browser")
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
