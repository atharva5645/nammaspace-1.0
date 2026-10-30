import json
import tempfile
import unittest
from pathlib import Path

from pipeline.filter.config import FilterConfig, Stage1Config, Stage2Config
from pipeline.filter.pipeline import FilterPipeline
from pipeline.filter.synthetic import generate_synthetic_ply_file


class TestFilterPipeline(unittest.TestCase):
    def test_full_pipeline_synthetic_execution(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_ply = tmp_path / "raw_synthetic.ply"
            out_dir = tmp_path / "filtered_output"

            # Create synthetic asset with known composition:
            # 100 valid + 5 nan + 10 bbox outliers + 5 scale outliers + 10 low opacity = 130 total
            generate_synthetic_ply_file(
                input_ply,
                num_valid=100,
                num_nan=5,
                num_bbox_outliers=10,
                num_scale_outliers=5,
                num_low_opacity=10,
                seed=99,
            )

            config = FilterConfig(
                stage1=Stage1Config(
                    remove_nan_inf=True,
                    bbox_min=[-2.0, -2.0, -2.0],
                    bbox_max=[2.0, 2.0, 2.0],
                    max_scale_exp=5.0,
                    min_opacity_raw=-5.0,
                ),
                stage2=Stage2Config(
                    enabled=True,
                    morton_order=True,
                    output_ply=True,
                    output_sog=True,
                    sh_iterations=2,
                ),
            )

            pipeline = FilterPipeline(config=config)
            report = pipeline.run(
                input_ply=input_ply,
                output_dir=out_dir,
                base_name="synthetic_twin",
            )

            self.assertEqual(report.status, "SUCCESS")
            self.assertEqual(report.stage1_stats["initial_count"], 130)
            self.assertEqual(report.stage1_stats["surviving_count"], 100)
            self.assertEqual(report.stage1_stats["nan_inf_culled"], 5)
            self.assertEqual(report.stage1_stats["bbox_culled"], 10)
            self.assertEqual(report.stage1_stats["scale_culled"], 5)
            self.assertEqual(report.stage1_stats["opacity_culled"], 10)

            # Check outputs
            report_file = out_dir / "filter_report.json"
            self.assertTrue(report_file.exists())

            with report_file.open("r", encoding="utf-8") as f:
                saved_report = json.load(f)
            self.assertEqual(saved_report["status"], "SUCCESS")

            stage1_ply = Path(saved_report["final_outputs"]["stage1_ply"])
            self.assertTrue(stage1_ply.exists())

            final_ply = Path(saved_report["final_outputs"]["final_ply"])
            self.assertTrue(final_ply.exists())

            final_sog = Path(saved_report["final_outputs"]["final_sog"])
            self.assertTrue(final_sog.exists())
            self.assertGreater(final_sog.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
