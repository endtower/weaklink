"""Build one launcher EXE plus editable manager/Core source and Python runtimes.

--private is for this machine only: retains existing Python configuration code,
does not produce public update packages or an embedded bootstrap payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_core_source import copy_runtime, copy_sources
from package_component import package
from update_policy import allowed_file, version_key
from workspace_layout import TOOLS


PUBLIC_COMPONENTS = ("core", "manager", "launcher")
MANAGER_SOURCE_FILES = (
    "manager.py", "manager_service.py", "manager_core.py", "manager_console.py", "manager_updates.py",
    "core_update_review.py", "update_policy.py", "component_versions.json", "startup_workflow.py", "startup_plan.py",
    "paths.py", "config_keys.py", "ingress_config.py", "truck_settings_store.py", "console_context.py", "console_history.py",
    "core/__init__.py", "core/supervisor.py",
    "utils/__init__.py", "utils/logger.py", "utils/error_handling.py", "utils/chain_context.py",
    "adapt/__init__.py", "adapt/bridge/__init__.py", "adapt/bridge/config.py", "adapt/bridge/contract.py",
    "docs/STARTUP.md",
)


def copy_manager_source(destination: Path, core_source: Path) -> None:
    for name in MANAGER_SOURCE_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / "manager_requirements.txt", destination / "requirements.txt")
    shutil.copy2(ROOT / "docs/STORAGE.md", destination / "STORAGE.md")
    # Manager can render its console before Core is installed. It needs only built assets.
    shutil.copytree(core_source / "web_frontend/dist", destination / "web_frontend/dist")


def validate_release_versions(versions, previous_releases):
    launcher_project = ElementTree.parse(ROOT / "launcher/AbyssLauncher.csproj")
    if launcher_project.findtext("./PropertyGroup/Version") != versions["launcher"]:
        raise ValueError("启动器项目版本与 component_versions.json 不一致")
    for component in PUBLIC_COMPONENTS:
        version_key(versions[component])
    if previous_releases is None:
        return
    for manifest in previous_releases.glob("*.json"):
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        component = previous.get("component")
        if component in PUBLIC_COMPONENTS and version_key(versions[component]) <= version_key(previous["version"]):
            raise ValueError(f"{component} {versions[component]} 必须高于已发布的 {previous['version']}，避免同版本生成不同的包")


def build(output: Path, private=False, feed_base_url="", package_base_url="", runtime=None, metadata_path=None, previous_releases=None):
    output = output.resolve()
    if output.exists():
        raise ValueError("输出必须为新目录，避免旧二进制或个人文件混入")
    versions = json.loads((ROOT / "component_versions.json").read_text(encoding="utf-8"))
    metadata = json.loads((metadata_path or ROOT / f"releases/core-{versions['core']}.json").read_text(encoding="utf-8"))
    if not private:
        validate_release_versions(versions, previous_releases)
    output.mkdir(parents=True)
    app = output / "app"
    core = app / "components/core"
    core.mkdir(parents=True)
    copy_sources(core / "source", private=private)
    if runtime:
        shutil.copytree(runtime, core / "runtime")
        locked = (runtime / "requirements.lock").read_text(encoding="utf-8")
    else:
        locked = copy_runtime(core / "runtime")
    (core / "runtime/requirements.lock").write_text(locked, encoding="utf-8")
    (core / "source/requirements.lock").write_text(locked, encoding="utf-8")
    (core / "release.json").write_text(json.dumps({**metadata, "version": versions["core"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Core source and runtime ready", flush=True)
    manager = app / "components/manager"
    copy_manager_source(manager / "source", core / "source")
    manager_lock = copy_runtime(manager / "runtime", requirements_path=ROOT / "manager_requirements.txt")
    (manager / "runtime/requirements.lock").write_text(manager_lock, encoding="utf-8")
    (manager / "source/requirements.lock").write_text(manager_lock, encoding="utf-8")
    (manager / "release.json").write_text(json.dumps({"version": versions["manager"], "format": "source-manager-v1"}), encoding="utf-8")
    shutil.copy2(ROOT / "component_versions.json", app / "component_versions.json")
    defaults = {"auto_check": not private, "core_distribution": "source-v1", "manager_distribution": "source-manager-v1", "sources": {
        name: feed_base_url.rstrip("/") + f"/{name}-latest.json" for name in PUBLIC_COMPONENTS if feed_base_url}}
    (app / "update_defaults.json").write_text(json.dumps(defaults, indent=2), encoding="utf-8")
    (app / "abyss-data-dir.txt").write_text("../data", encoding="utf-8")
    (app / "abyss-storage-dir.txt").write_text("..", encoding="utf-8")
    bundle = None
    if not private:
        bundle = output / "bootstrap.zip"
        entries = [p for p in manager.rglob("*") if p.is_file() and allowed_file("manager", p.relative_to(app).as_posix())]
        entries += [app / "component_versions.json", app / "update_defaults.json"]
        manifest = {}
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in entries:
                name = path.relative_to(app).as_posix()
                with path.open("rb") as stream:
                    manifest[name] = hashlib.file_digest(stream, "sha256").hexdigest()
                archive.write(path, name)
            archive.writestr("bootstrap.manifest.json", json.dumps(manifest))
    dotnet = TOOLS / "dotnet/dotnet.exe"
    command = [str(dotnet) if dotnet.is_file() else "dotnet", "publish", str(ROOT / "launcher/AbyssLauncher.csproj"), "-c", "Release", "-r", "win-x64", "--self-contained", "true",
               "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=true", "-p:NuGetAudit=false",
               "-p:RestoreIgnoreFailedSources=true",
               "-o", str(output / "launcher-build"), "--nologo"]
    if (TOOLS / "dotnet/packs").is_dir():
        command.append("-p:RestoreSources=" + str(TOOLS / "dotnet/packs"))
    if bundle:
        command.append("-p:BootstrapBundle=" + str(bundle))
    subprocess.run(command, check=True, cwd=ROOT)
    shutil.copy2(output / "launcher-build/AbyssLauncher.exe", app / "AbyssLauncher.exe")
    if not private:
        # Manager 0.11.0 also checks for manager_internal/ when importing a source package.
        legacy_manager = app / "manager_internal"
        legacy_manager.mkdir()
        (legacy_manager / "source-layout.txt").write_text("components/manager/runtime\n", encoding="utf-8")
        if previous_releases:
            (output / "packages").mkdir(exist_ok=True)
            for path in previous_releases.glob("*.json"):
                if not path.name.endswith(("-latest.json", "-versions.json")):
                    shutil.copy2(path, output / "packages" / path.name)
        for name in PUBLIC_COMPONENTS:
            package(name, versions[name], app, output / "packages", package_base_url, metadata=metadata if name == "core" else None)
        (output / "download").mkdir()
        shutil.copy2(app / "AbyssLauncher.exe", output / "download/AbyssLauncher.exe")
    summary = {"app": str(app), "versions": versions, "private": private, "packaged_business_executables": ["AbyssLauncher.exe"]}
    (output / "build-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--feed-base-url", default="")
    parser.add_argument("--package-base-url", default="")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--previous-releases", type=Path)
    args = parser.parse_args()
    build(args.output, args.private, args.feed_base_url, args.package_base_url, args.runtime, args.metadata, args.previous_releases)


if __name__ == "__main__":
    main()
