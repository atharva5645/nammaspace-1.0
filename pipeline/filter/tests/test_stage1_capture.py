import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

from pipeline.filter.config import CaptureFilterConfig
from pipeline.filter.stage1_capture import (
    compute_laplacian_variance,
    compute_exposure_metrics,
    compute_frame_similarity,
    run_stage1_capture,
)


class TestStage1Capture(unittest.TestCase):
    def create_sharp_image(self, width: int = 256, height: int = 256, pattern_seed: int = 1) -> np.ndarray:
        """Create high-contrast synthetic image with sharp geometric edges."""
        img = np.zeros((height, width, 3), dtype=np.uint8)
        # Background mid-tone
        img[:] = 120
        # Draw high-contrast shapes and lines
        cv2.rectangle(img, (20, 20), (width - 20, height - 20), (240, 240, pattern_seed * 40 % 255), 3)
        cv2.circle(img, (width // 2, height // 2), 40, (10, 10, 200), -1)
        for i in range(10, width, 20):
            cv2.line(img, (i, 0), (i, height), (255, 255, 255), 1)
        return img

    def test_blur_detection(self):
        sharp = self.create_sharp_image()
        sharp_var = compute_laplacian_variance(sharp)
        self.assertGreater(sharp_var, 150.0, f"Sharp image variance should be high, got {sharp_var}")

        # Heavy Gaussian blur to simulate severe motion/focus blur
        blurred = cv2.GaussianBlur(sharp, (31, 31), 10.0)
        blur_var = compute_laplacian_variance(blurred)
        self.assertLess(blur_var, 40.0, f"Blurred image variance should be low, got {blur_var}")

    def test_exposure_detection(self):
        # 1. Normal exposure
        normal = self.create_sharp_image()
        normal_exp = compute_exposure_metrics(normal)
        self.assertGreaterEqual(normal_exp["mean_luminance"], 35.0)
        self.assertLessEqual(normal_exp["mean_luminance"], 225.0)

        # 2. Severe under-exposure (pitch black / dark shadow)
        dark = np.ones((128, 128, 3), dtype=np.uint8) * 10
        dark_exp = compute_exposure_metrics(dark)
        self.assertLess(dark_exp["mean_luminance"], 20.0)
        self.assertGreater(dark_exp["shadow_ratio"], 0.8)

        # 3. Severe over-exposure (washed out / highlight blowout)
        bright = np.ones((128, 128, 3), dtype=np.uint8) * 250
        bright_exp = compute_exposure_metrics(bright)
        self.assertGreater(bright_exp["mean_luminance"], 240.0)
        self.assertGreater(bright_exp["highlight_ratio"], 0.8)

    def test_near_duplicate_detection(self):
        img_a = self.create_sharp_image(pattern_seed=1)
        # Near-duplicate: identical image with +/- 1 intensity jitter (subtle sensor noise)
        noise = np.random.randint(-1, 2, img_a.shape).astype(np.int16)
        img_near_dup = np.clip(img_a.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        dup_sim = compute_frame_similarity(img_near_dup, img_a)
        self.assertGreater(dup_sim, 0.95, f"Near duplicate similarity should be >0.95, got {dup_sim}")

        # Completely distinct image with inverted colors and different geometry
        img_different = np.zeros_like(img_a)
        img_different[:] = (40, 200, 40)
        cv2.rectangle(img_different, (50, 50), (200, 200), (255, 10, 10), -1)

        diff_sim = compute_frame_similarity(img_different, img_a)
        self.assertLess(diff_sim, 0.70, f"Distinct image similarity should be low, got {diff_sim}")

    def test_even_frame_cap_decimation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_dir = tmp_path / "input_frames"
            in_dir.mkdir()

            # Create 10 distinct, sharp images
            for i in range(10):
                img = self.create_sharp_image(pattern_seed=i + 1)
                # Shift background to ensure each is distinct
                img[:] = np.clip(img.astype(np.int16) + (i * 10), 0, 255).astype(np.uint8)
                cv2.imwrite(str(in_dir / f"frame_{i:03d}.jpg"), img)

            # Filter with cap of 4 frames
            config = CaptureFilterConfig(
                min_laplacian_var=10.0,
                near_duplicate_threshold=0.999,
                max_frames_cap=4,
            )
            res = run_stage1_capture(in_dir, tmp_path / "out", config)
            self.assertTrue(res.success)
            self.assertEqual(res.kept_frames_count, 4)
            self.assertEqual(res.dropped_counts["frame_cap_decimated"], 6)

    def test_full_stage1_folder_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            in_dir = tmp_path / "synthetic_capture"
            in_dir.mkdir()
            out_dir = tmp_path / "stage1_output"

            # Frame 0: Valid Sharp Reference
            f0 = self.create_sharp_image(pattern_seed=1)
            cv2.imwrite(str(in_dir / "frame_00.jpg"), f0)

            # Frame 1: Blurred copy of Frame 0
            f1 = cv2.GaussianBlur(f0, (31, 31), 10.0)
            cv2.imwrite(str(in_dir / "frame_01.jpg"), f1)

            # Frame 2: Under-exposed (dark)
            f2 = np.ones((256, 256, 3), dtype=np.uint8) * 10
            cv2.imwrite(str(in_dir / "frame_02.jpg"), f2)

            # Frame 3: Over-exposed (white blowout)
            f3 = np.ones((256, 256, 3), dtype=np.uint8) * 250
            cv2.imwrite(str(in_dir / "frame_03.jpg"), f3)

            # Frame 4: Near-duplicate of Frame 0
            f4 = f0.copy()
            cv2.imwrite(str(in_dir / "frame_04.jpg"), f4)

            # Frame 5: Second valid sharp frame (novel camera position / geometry)
            f5 = np.zeros((256, 256, 3), dtype=np.uint8)
            f5[:] = 90
            cv2.rectangle(f5, (40, 40), (220, 220), (0, 255, 255), 4)
            for x in range(0, 256, 15):
                cv2.line(f5, (x, 0), (256 - x, 256), (255, 0, 150), 2)
            cv2.imwrite(str(in_dir / "frame_05.jpg"), f5)

            config = CaptureFilterConfig(
                min_laplacian_var=60.0,
                min_mean_luminance=35.0,
                max_mean_luminance=225.0,
                near_duplicate_threshold=0.92,
            )

            res = run_stage1_capture(in_dir, out_dir, config)
            self.assertTrue(res.success)
            self.assertEqual(res.total_frames_extracted, 6)
            self.assertEqual(res.kept_frames_count, 2)  # Frames 0 and 5 kept

            self.assertEqual(res.dropped_counts["blur_detected"], 1)
            self.assertEqual(res.dropped_counts["under_exposed"], 1)
            self.assertEqual(res.dropped_counts["over_exposed"], 1)
            self.assertEqual(res.dropped_counts["near_duplicate"], 1)

            # Verify output files in stage1 folder
            stage1_folder = out_dir / "stage1"
            self.assertTrue(stage1_folder.exists())
            kept_files = sorted(list(stage1_folder.glob("*.jpg")))
            self.assertEqual(len(kept_files), 2)

            manifest_file = stage1_folder / "frames_manifest.json"
            self.assertTrue(manifest_file.exists())
            with manifest_file.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            self.assertEqual(len(manifest_data), 2)
            self.assertEqual(manifest_data[0]["original_filename"], "frame_00.jpg")
            self.assertEqual(manifest_data[1]["original_filename"], "frame_05.jpg")


if __name__ == "__main__":
    unittest.main()
