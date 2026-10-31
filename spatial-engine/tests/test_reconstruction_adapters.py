import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ingest = _load_module("nammaspace_test_ingest", ROOT / "reconstruction" / "ingest.py")
sfm_adapter = _load_module("nammaspace_test_sfm_adapter", ROOT / "reconstruction" / "sfm_adapter.py")


class ImageIngestTests(unittest.TestCase):
    def test_ingest_binds_normalized_image_to_source_and_applies_exif_orientation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            storage = root / "storage"
            workspace = root / "job"
            storage.mkdir()
            workspace.mkdir()
            original = Image.new("RGB", (80, 120), "white")
            exif = Image.Exif()
            exif[274] = 6
            original.save(storage / "room.jpg", exif=exif)
            digest = hashlib.sha256((storage / "room.jpg").read_bytes()).hexdigest()

            result = ingest.prepare_capture_images(
                [{"upload_id": "upload-1", "sha256": digest, "category": "room_image", "side": "side1",
                  "content_type": "image/jpeg", "storage_key": "room.jpg"}],
                storage,
                workspace,
            )

            self.assertEqual(result.image_count, 1)
            self.assertEqual(result.manifest["images"][0]["upload_id"], "upload-1")
            self.assertEqual(result.manifest["images"][0]["side"], "side1")
            self.assertEqual((result.manifest["images"][0]["width_px"], result.manifest["images"][0]["height_px"]), (120, 80))
            self.assertTrue(result.manifest["images"][0]["exif_orientation_applied"])
            self.assertTrue(result.manifest_path.is_file())

    def test_ingest_rejects_checksum_mismatch_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            storage = root / "storage"
            workspace = root / "job"
            storage.mkdir()
            workspace.mkdir()
            Image.new("RGB", (80, 80), "white").save(storage / "room.jpg")
            base = {"upload_id": "upload-1", "category": "room_image", "side": "side1",
                    "content_type": "image/jpeg", "storage_key": "room.jpg"}
            checksum_workspace = workspace / "checksum"
            checksum_workspace.mkdir()
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                ingest.prepare_capture_images([{**base, "sha256": "0" * 64}], storage, checksum_workspace)

            Image.new("RGB", (80, 80), "white").save(root / "outside.jpg")
            outside_hash = hashlib.sha256((root / "outside.jpg").read_bytes()).hexdigest()
            escape_workspace = workspace / "escape"
            escape_workspace.mkdir()
            with self.assertRaisesRegex(ValueError, "escapes"):
                ingest.prepare_capture_images([{**base, "storage_key": "../outside.jpg", "sha256": outside_hash}], storage, escape_workspace)


class SparseSfmAdapterTests(unittest.TestCase):
    def test_missing_toolchain_reports_actionable_codes(self):
        with patch.object(sfm_adapter.shutil, "which", return_value=None), patch.object(sfm_adapter.sysconfig, "get_path", return_value=""):
            with self.assertRaises(sfm_adapter.SfMToolchainUnavailable) as capture_missing:
                sfm_adapter.run_sparse_sfm(Path("images"), Path("out"))
        self.assertEqual(capture_missing.exception.code, "capture_splat_cli_missing")

        with patch.object(sfm_adapter.shutil, "which", side_effect=["capture-splat", None]):
            with self.assertRaises(sfm_adapter.SfMToolchainUnavailable) as colmap_missing:
                sfm_adapter.run_sparse_sfm(Path("images"), Path("out"))
        self.assertEqual(colmap_missing.exception.code, "colmap_binary_missing")

    def test_adapter_falls_back_to_interpreter_script_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            script_dir = Path(temporary)
            script = script_dir / ("capture-splat.exe" if os.name == "nt" else "capture-splat")
            script.write_text("", encoding="utf-8")
            with patch.object(sfm_adapter.shutil, "which", return_value=None), patch.object(sfm_adapter.sysconfig, "get_path", return_value=str(script_dir)):
                with self.assertRaises(sfm_adapter.SfMToolchainUnavailable) as missing_colmap:
                    sfm_adapter.run_sparse_sfm(Path("images"), Path("out"))
            self.assertEqual(missing_colmap.exception.code, "colmap_binary_missing")

    def test_sparse_run_requires_summary_and_camera_point_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            output = root / "out"

            def fake_run(command, **_kwargs):
                output_dir = Path(command[command.index("--out") + 1])
                (output_dir / "capture_splat_sfm_summary.json").write_text(json.dumps({"decision": "promote"}), encoding="utf-8")
                sparse = output_dir / "sparse" / "0"
                sparse.mkdir(parents=True)
                (sparse / "images.txt").write_text("# cameras\n", encoding="utf-8")
                (sparse / "points3D.txt").write_text("# points\n", encoding="utf-8")
                return sfm_adapter.subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(sfm_adapter.shutil, "which", side_effect=["capture-splat", "colmap"]), patch.object(sfm_adapter.subprocess, "run", side_effect=fake_run):
                result = sfm_adapter.run_sparse_sfm(images, output)

            self.assertEqual(result.summary["decision"], "promote")
            self.assertTrue(result.camera_poses_path.is_file())
            self.assertTrue(result.sparse_points_path.is_file())


if __name__ == "__main__":
    unittest.main()
