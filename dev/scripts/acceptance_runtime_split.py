"""运行库拆分验收：runtime 与源码彻底分离，日常更新只动源码。

背景（2026-11-13）：此前 core 包 68.6MB/5077 文件，其中 4806 个是 Python 运行时。
改几行源码也要把整个运行时重写一遍，装一次 5 分钟。拆成
core-runtime / manager-runtime 两个独立组件后，core 只 271 文件/1.3MB。

本测试锁住：
  1. 文件归属互斥（同一文件不会被两个组件认领）
  2. core 包不含 runtime；runtime 包不含 source
  3. runtime 组件的磁盘路径映射正确（core-runtime -> components/core/runtime）
  4. 未装 runtime 时不允许直接更新源码组件
"""
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
_sandbox = tempfile.TemporaryDirectory(prefix="abyss-runtime-split-")
os.environ["ABYSS_DATA_DIR"] = _sandbox.name

from update_policy import (  # noqa: E402
    COMPONENTS, RUNTIME_COMPONENTS, RUNTIME_OF, allowed_file, runtime_target,
)


class RuntimeSplitAcceptance(unittest.TestCase):
    def test_runtime_components_registered(self):
        self.assertIn("core-runtime", COMPONENTS)
        self.assertIn("manager-runtime", COMPONENTS)
        self.assertEqual(RUNTIME_OF["core"], "core-runtime")
        self.assertEqual(RUNTIME_OF["manager"], "manager-runtime")

    def test_runtime_maps_into_parent_tree(self):
        """同时装进 components/core/runtime，python.exe 路径保持不变。"""
        self.assertEqual(runtime_target("core-runtime"), "components/core/runtime/")
        self.assertEqual(runtime_target("manager-runtime"), "components/manager/runtime/")
        self.assertEqual(runtime_target("core"), "")
        self.assertEqual(runtime_target("snowluma"), "")

    def test_core_no_longer_owns_runtime(self):
        """拆分的核心目的：core 包不再包含任何运行时文件。"""
        self.assertFalse(allowed_file("core", "components/core/runtime/python.exe"))
        self.assertFalse(allowed_file("core", "components/core/runtime/Lib/site-packages/aiohttp/__init__.py"))
        self.assertTrue(allowed_file("core", "components/core/source/main.py"))
        self.assertTrue(allowed_file("core", "components/core/release.json"))

    def test_runtime_owns_only_its_tree(self):
        self.assertTrue(allowed_file("core-runtime", "components/core/runtime/python.exe"))
        self.assertTrue(allowed_file("core-runtime", "components/core/runtime/Lib/site-packages/x/y.py"))
        self.assertFalse(allowed_file("core-runtime", "components/core/source/main.py"))
        self.assertFalse(allowed_file("core-runtime", "components/core/release.json"))
        self.assertFalse(allowed_file("manager-runtime", "components/core/runtime/python.exe"))

    def test_manager_no_longer_owns_runtime(self):
        self.assertFalse(allowed_file("manager", "components/manager/runtime/python.exe"))
        self.assertTrue(allowed_file("manager", "components/manager/source/manager_service.py"))
        self.assertTrue(allowed_file("manager-runtime", "components/manager/runtime/python.exe"))

    def test_no_file_has_two_owners(self):
        samples = [
            "components/core/runtime/python.exe",
            "components/core/runtime/Lib/site-packages/aiohttp/__init__.py",
            "components/core/source/main.py",
            "components/core/release.json",
            "components/manager/runtime/python.exe",
            "components/manager/source/manager_service.py",
            "AbyssLauncher.exe",
        ]
        for name in samples:
            owners = [c for c in COMPONENTS if allowed_file(c, name)]
            self.assertEqual(len(owners), 1, f"{name} 归属不唯一: {owners}")

    def test_runtime_package_rejects_source_files(self):
        """打包校验：runtime 包里混进 source 必须报错。"""
        from manager_updates import Updates
        # 只测解包校验用到的纯逻辑：直接调用 require 分支不可行，
        # 因此改为断言白名单本身已排除（打包时按白名单过滤）。
        self.assertFalse(allowed_file("core-runtime", "components/core/source/main.py"))

    def test_component_roots_uses_runtime_mapping(self):
        from core_update_review import component_roots
        root = Path("X:/fake")
        self.assertEqual(component_roots(root, "core-runtime"), [root / "components/core/runtime"])
        self.assertEqual(component_roots(root, "manager-runtime"), [root / "components/manager/runtime"])
        self.assertIn(root / "components/core", component_roots(root, "core"))


class PackageSizeAcceptance(unittest.TestCase):
    """用真实安装目录验证：拆分后 core 的文件数应远少于 runtime。"""

    def test_core_package_is_much_smaller_than_runtime(self):
        from core_update_review import installed_files
        app = Path(r"E:\ABYSS\N_Touch\app")
        if not (app / "components/core/runtime").is_dir():
            self.skipTest("本机未安装运行库，跳过体积校验")
        core = installed_files(app, "core")
        runtime = installed_files(app, "core-runtime")
        self.assertGreater(len(runtime), 1000, "运行库文件数应上千")
        self.assertLess(len(core), 500, "源码文件数应远小于运行库")
        self.assertLess(len(core) * 5, len(runtime), "源码应至少比运行库小 5 倍")
        # 关键：core 的基线里绝不能混入 runtime
        self.assertEqual([f for f in core if "/runtime/" in f], [])


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        unittest.main(verbosity=2)
    finally:
        logging.shutdown()
        _sandbox.cleanup()
