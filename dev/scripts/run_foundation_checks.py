"""Run the fast regressions using the same public Python defaults as a release."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_core_source import copy_python_sources
from workspace_layout import test_root


CHECKS = (
    "acceptance_data_paths.py",
    "acceptance_db_race.py",
    "acceptance_error_boundaries.py",
    "acceptance_pre_lifecycle.py",
    "acceptance_reflection_compensation.py",
    "acceptance_critical_actions.py",
)


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
        for name in CHECKS:
            print(f"Running {name}", flush=True)
            result = subprocess.run([sys.executable, "-B", str(scripts / name)], cwd=source, env=env)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
