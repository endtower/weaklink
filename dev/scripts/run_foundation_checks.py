"""Run the fast regressions using the same public Python defaults as a release."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_core_source import copy_python_sources
from build_source_distribution import copy_manager_source
from workspace_layout import test_root


CHECKS = (
    "acceptance_data_paths.py",
    "acceptance_db_race.py",
    "acceptance_error_boundaries.py",
    "acceptance_pre_lifecycle.py",
    "acceptance_reflection_compensation.py",
    "acceptance_critical_actions.py",
)


def check_manager_import(root: Path, env: dict[str, str]) -> int:
    frontend = root / "frontend"
    dist = frontend / "web_frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<title>Fixture</title>", encoding="utf-8")
    manager = root / "app" / "components" / "manager"
    source = manager / "source"
    copy_manager_source(source, frontend)
    (manager / "release.json").write_text("{}", encoding="utf-8")
    print("Checking the standalone Manager import and process specifications", flush=True)
    result = subprocess.run([sys.executable, "-B", "-c",
                             "import sys; sys.path.insert(0, sys.argv[1]); "
                             "import manager_service; from manager_core import build_specs; "
                             "assert {'ingress', 'core'} <= build_specs().keys()", str(source)],
                            cwd=source, env=env)
    return result.returncode


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="foundation-", dir=test_root()) as tmp:
        root = Path(tmp)
        source = root / "source"
        copy_python_sources(source)
        scripts = source / "scripts"
        scripts.mkdir()
        for name in ("workspace_layout.py", *CHECKS):
            shutil.copy2(Path(__file__).with_name(name), scripts / name)
        env = {**os.environ, "ABYSS_DATA_DIR": str(root / "data"), "LOG_GLOBAL_FILE": "0",
               "PYTHONDONTWRITEBYTECODE": "1"}
        manager_result = check_manager_import(root, env)
        if manager_result:
            return manager_result
        for name in CHECKS:
            print(f"Running {name}", flush=True)
            result = subprocess.run([sys.executable, "-B", str(scripts / name)], cwd=source, env=env)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
