import tempfile
import unittest
from pathlib import Path

from pipeline.filter.config import Stage2Config
from pipeline.filter.stage2_transform import (
    find_splat_transform_cli,
    verify_splat_transform_tool,
    build_actions_list,
    run_stage2_transform,
)
from pipeline.filter.synthetic import generate_synthetic_ply_file


class TestStage2Transform(unittest.TestCase):
    def test_tool_discovery_and_verification(self):
        cli = find_splat_transform_cli()
        self.assertIsNotNone(cli, "splat-transform cli.mjs should be discovered in the repo")
        self.assertTrue(cli.exists(), f"Discovered path must exist: {cli}")

        info = verify_splat_transform_tool(cli)
        self.assertTrue(info["available"], f"Tool verification failed: {info.get('error')}")
        self.assertIn("splat-transform", info.get("version", ""))

    def test_build_actions(self):
        config = Stage2Config(
            filter_floaters="0.05,0.1,0.004",
            filter_harmonics=2,
            morton_order=True,
            seed_pos=[0.0, 1.0, 0.0],
        )
        actions = build_actions_list(config)
        self.assertIn("--seed-pos", actions)
        self.assertIn("0.0,1.0,0.0", actions)
        self.assertIn("--filter-floaters=0.05,0.1,0.004", actions)
        self.assertIn("-H", actions)
        self.assertIn("2", actions)
        self.assertIn("-m", actions)

    def test_run_stage2_on_synthetic_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            synth_ply, _ = generate_synthetic_ply_file(
                tmp_path / "input.ply",
                num_valid=50,
                num_nan=0,
                num_bbox_outliers=0,
                num_scale_outliers=0,
                num_low_opacity=0,
            )

            # Test Stage 2 with morton order and SOG conversion
            config = Stage2Config(
                enabled=True,
                morton_order=True,
                output_ply=True,
                output_sog=True,
                sh_iterations=2,
            )

            res = run_stage2_transform(
                input_ply=synth_ply,
                output_dir=tmp_path / "out",
                config=config,
                base_name="synth_stage2",
            )

            self.assertTrue(res.success, f"Stage 2 failed: {res.error}\nLogs:\n{res.logs}")
            self.assertIsNotNone(res.output_ply)
            self.assertTrue(res.output_ply.exists())
            self.assertGreater(res.ply_size_bytes, 0)

            self.assertIsNotNone(res.output_sog)
            self.assertTrue(res.output_sog.exists())
            self.assertGreater(res.sog_size_bytes, 0)


if __name__ == "__main__":
    unittest.main()
