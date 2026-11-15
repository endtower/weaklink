"""程序与数据分离的路径回归；不读取或修改实际用户数据。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from workspace_layout import test_root
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths
import ingress_config
from core import supervisor

TEMP_ROOT = test_root()
TEMP_ROOT.mkdir(exist_ok=True)


class DataPathsTests(unittest.TestCase):
    def test_package_descriptor_is_relative_to_program_not_cwd(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            app = root / "dist" / "preview"
            app.mkdir(parents=True)
            (app / "abyss-data-dir.txt").write_text("../..\n", encoding="utf-8")
            with patch.dict(os.environ, {"ABYSS_DATA_DIR": ""}), patch("paths.app_root", return_value=app):
                self.assertEqual(paths.data_root(), root.resolve())

    def test_environment_overrides_descriptor_and_new_default_is_separated(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"ABYSS_DATA_DIR": ""}), patch("paths.app_root", return_value=root):
                self.assertEqual(paths.data_root(), root / "data")
                (root / "abyss-data-dir.txt").write_text("missing", encoding="utf-8")
                with self.assertRaises(FileNotFoundError):
                    paths.data_root()
                with patch.dict(os.environ, {"ABYSS_DATA_DIR": str(root)}):
                    self.assertEqual(paths.data_root(), root.resolve())

    def test_selected_profile_never_falls_back_to_program_environment(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            app, profile = root / "app", root / "profile"
            app.mkdir()
            profile.mkdir()
            (app / ".env.dev").write_text("INGRESS_API_PORT=45678\nWEB_WS_PORT=45679\n", encoding="utf-8")
            env = {key: value for key, value in os.environ.items()
                   if key not in {"INGRESS_API_PORT", "WEB_WS_PORT", "ONEBOT_WS_PORT", "FIXTURE_WEB_PORT"}}
            env["ABYSS_DATA_DIR"] = str(profile)
            with patch.dict(os.environ, env, clear=True), patch("paths.app_root", return_value=app):
                self.assertEqual(paths.data_env_path(), profile / ".env.dev")
                paths.load_data_env()
                self.assertNotIn("INGRESS_API_PORT", os.environ)
                self.assertEqual(ingress_config.api_port(), 5003)
                self.assertEqual(supervisor.core_ports(), (5002, 5001))

                (profile / ".env.dev").write_text(
                    "INGRESS_API_PORT=45680\nFIXTURE_WEB_PORT=45681\nWEB_WS_PORT=${FIXTURE_WEB_PORT}\n",
                    encoding="utf-8",
                )
                self.assertEqual(ingress_config.api_port(), 45680)
                self.assertEqual(supervisor.core_ports(), (45681, 5001))
                os.environ["FIXTURE_WEB_PORT"] = "45682"
                self.assertEqual(supervisor.core_ports(), (45682, 5001))
                paths.load_data_env()
                self.assertEqual(os.environ["INGRESS_API_PORT"], "45680")
                self.assertEqual(supervisor.core_ports(), (45682, 5001))
                self.assertEqual(ingress_config.settings()["WEB_WS_PORT"], "45682")
                os.environ["WEB_WS_PORT"] = "45683"
                self.assertEqual(supervisor.core_ports(), (45683, 5001))

    def test_legacy_data_stays_in_place_and_managed_core_shares_installation(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            app = root / "app"
            app.mkdir()
            with patch.dict(os.environ, {"ABYSS_DATA_DIR": ""}), patch("paths.app_root", return_value=app):
                self.assertEqual(paths.data_root(), root / "data")
                (app / ".env.dev").write_text("# synthetic legacy profile")
                self.assertEqual(paths.data_root(), app)
                self.assertEqual(paths.cache_root(), root / "cache")
                self.assertEqual(paths.backup_root(), root / "backups")
                self.assertEqual(paths.external_root(), root / "external")
            source = app / "components/core/source"
            source.mkdir(parents=True)
            (source.parent / "release.json").write_text("{}")
            with patch.dict(os.environ, {"ABYSS_DATA_DIR": ""}), patch("paths.app_root", return_value=source):
                self.assertEqual(paths.data_root(), root / "data")
                self.assertEqual(paths.cache_root(), root / "cache")

    def test_snowluma_preserves_existing_location_and_uses_external_for_new_install(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            app, data = root / "app", root / "data"
            app.mkdir(); data.mkdir()
            with patch.dict(os.environ, {"ABYSS_SNOWLUMA_DIR": ""}), \
                    patch.object(supervisor, "app_root", return_value=app), \
                    patch.object(supervisor, "data_root", return_value=data), \
                    patch.object(supervisor, "external_root", return_value=root / "external"):
                self.assertEqual(supervisor.snowluma_root(), root / "external/snowluma")
                (app / "SnowLuma").mkdir()
                self.assertEqual(supervisor.snowluma_root(), app / "SnowLuma")
                (data / "SnowLuma").mkdir()
                self.assertEqual(supervisor.snowluma_root(), data / "SnowLuma")
                with patch.dict(os.environ, {"ABYSS_SNOWLUMA_DIR": str(root / "user-chosen")}):
                    self.assertEqual(supervisor.snowluma_root(), root / "user-chosen")

    def test_empty_descriptor_does_not_silently_create_an_empty_profile(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            root = Path(tmp)
            (root / "abyss-data-dir.txt").write_text("\n", encoding="utf-8")
            with patch.dict(os.environ, {"ABYSS_DATA_DIR": ""}), patch("paths.app_root", return_value=root):
                with self.assertRaises(ValueError):
                    paths.data_root()


if __name__ == "__main__":
    unittest.main()
