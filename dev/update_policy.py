"""Shared package boundary: update program files, never runtime/user data."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

COMPONENTS = ("core", "snowluma", "ingress", "manager", "launcher", "core-runtime", "manager-runtime")
LOCALES = {"cs", "de", "es", "fr", "it", "ja", "ko", "pl", "pt-BR", "ru", "tr", "zh-Hans", "zh-Hant"}

# 运行库独立成组件（2026-11-13）：此前 core/manager 的包各自带上整套 Python
# 运行时（core 142MB/4806 文件、manager 109MB/3808 文件），改几行源码也要把
# 运行库整个重写一遍。现在把 runtime 拆出来单独发版，日常更新只动几 MB 源码。
#
# 组件名与安装路径解耦：`core-runtime` 装进 `components/core/runtime`，
# 与 `core` 同一棵树，所以 python.exe 路径、._pth、启动脚本全都不用改。
RUNTIME_COMPONENTS = {
    "core-runtime": "components/core/runtime/",
    "manager-runtime": "components/manager/runtime/",
}
# 组件 -> 它依赖的运行库组件（安装/更新时必须先就位）
RUNTIME_OF = {"core": "core-runtime", "manager": "manager-runtime"}

# 源码组件（不含运行库）——发布、更新、版本展示都以这组为准。
SOURCE_COMPONENTS = ("core", "manager", "ingress", "snowluma", "launcher")

CORE_SOURCE = "components/core/source/"
CORE_RUNTIME = "components/core/runtime/"
MANAGER_RUNTIME = "components/manager/runtime/"


def runtime_target(component: str) -> str:
    """该组件对应运行库的安装前缀（相对 app/）；没有独立运行库则空串。"""
    return RUNTIME_COMPONENTS.get(component, "")


def core_source_file(name: str) -> bool:
    """可修改的程序源码；用户数据始终在独立 data_root。"""
    if not name.startswith(CORE_SOURCE):
        return False
    relative = name[len(CORE_SOURCE):]
    parts = relative.split("/")
    if any(p.startswith(".env") and p != ".env.example" for p in parts):
        return False
    if any(p in ("__pycache__", ".git", "node_modules", "logs", "data", "persistence", "history") for p in parts):
        return False
    if relative.startswith("web_frontend/dist/"):
        return True
    if relative.startswith(("web_frontend/src/", "web_frontend/public/")):
        return True
    if relative.startswith("web_frontend/") and relative.count("/") == 1:
        return relative.endswith((".json", ".ts", ".html"))
    return relative.endswith((".py", ".md")) or relative in ("requirements.txt", "requirements.lock", ".env.example")


def safe_relative(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError(f"Invalid package path: {name!r}")
    parts = name.split("/")
    if any(p in ("", ".", "..") or p.endswith((".", " ")) or any(ord(c) < 32 for c in p)
           or any(c in p for c in '<>"|?*')
           or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
           for p in parts):
        raise ValueError(f"Invalid package path: {name!r}")
    return str(PurePosixPath(name))


def allowed_file(component: str, name: str) -> bool:
    name = safe_relative(name)
    parts = name.split("/")
    # 运行库组件：只认自己那棵 runtime/ 子树，且必须有实际内容（禁止空目录条目）。
    prefix = RUNTIME_COMPONENTS.get(component)
    if prefix is not None:
        return (name.startswith(prefix) and len(parts) > 3
                and not any(p in ("__pycache__", ".git") for p in parts))
    if component == "manager" and name.startswith("components/manager/"):
        # manager 与 core 共用同一套源码白名单（只换前缀）；runtime 已归 manager-runtime，
        # 不再从 core 白名单继承，避免两个组件写到同一批文件。
        return allowed_file("core", "components/core/" + name[len("components/manager/"):])
    if component == "core" and name.startswith("components/core/"):
        # 不再包含 CORE_RUNTIME：运行库归 core-runtime 组件。
        return name == "components/core/release.json" or core_source_file(name)
    if component in ("core", "manager", "ingress"):
        return name == f"{component}.exe" or (len(parts) > 1 and parts[0] == f"{component}_internal")
    if component == "snowluma":
        if len(parts) > 1:
            return parts[0] in ("native", "client", "webui")
        return name in ("index.mjs", "launcher.bat", "node.exe", "package.json", "package-lock.json",
                        "release.json") \
            or name.endswith((".js", ".mjs", ".cjs", ".md")) or name in ("LICENSE", "LICENSE.txt")
    if component == "launcher":
        if len(parts) > 1:
            return parts[0] in LOCALES | {"runtimes"} or name == "updater/AbyssUpdater.exe"
        return name.endswith(".dll") or name in (
            "AbyssLauncher.exe", "AbyssLauncher.deps.json", "AbyssLauncher.runtimeconfig.json", "createdump.exe")
    return False


def version_key(version: str) -> tuple:
    """SemVer comparison (including numeric prerelease identifiers); build metadata is ignored."""
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", version)
    if not match:
        raise ValueError(f"Invalid version: {version!r}")
    pre = match[4]
    ids = tuple((0, int(x)) if x.isdigit() else (1, x) for x in pre.split(".")) if pre else ()
    return (int(match[1]), int(match[2]), int(match[3]), pre is None, ids)
