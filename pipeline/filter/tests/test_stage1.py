import unittest
import numpy as np

from pipeline.filter.config import Stage1Config
from pipeline.filter.stage1_filter import run_stage1_filter
from pipeline.filter.synthetic import create_synthetic_3dgs_data


class TestStage1Filter(unittest.TestCase):
    def setUp(self):
        self.data, self.counts = create_synthetic_3dgs_data(
            num_valid=100,
            num_nan=5,
            num_bbox_outliers=10,
            num_scale_outliers=4,
            num_low_opacity=8,
            seed=42,
        )

    def test_nan_culling(self):
        config = Stage1Config(
            remove_nan_inf=True,
            bbox_min=None,
            bbox_max=None,
            max_scale_exp=None,
            min_opacity_raw=None,
        )
        res = run_stage1_filter(self.data, config)
        self.assertEqual(res.stats["nan_inf_culled"], 5)
        self.assertEqual(res.stats["surviving_count"], len(self.data) - 5)

    def test_bbox_culling(self):
        config = Stage1Config(
            remove_nan_inf=True,
            bbox_min=[-2.0, -2.0, -2.0],
            bbox_max=[2.0, 2.0, 2.0],
            max_scale_exp=None,
            min_opacity_raw=None,
        )
        res = run_stage1_filter(self.data, config)
        # NaN is culled first (5), then bbox outliers at ~50m are culled (10)
        self.assertEqual(res.stats["nan_inf_culled"], 5)
        self.assertEqual(res.stats["bbox_culled"], 10)

    def test_scale_culling(self):
        config = Stage1Config(
            remove_nan_inf=True,
            bbox_min=None,
            bbox_max=None,
            max_scale_exp=5.0,  # exp(10) > 22000 > 5.0
            min_opacity_raw=None,
        )
        res = run_stage1_filter(self.data, config)
        self.assertEqual(res.stats["scale_culled"], 4)

    def test_opacity_culling(self):
        config = Stage1Config(
            remove_nan_inf=True,
            bbox_min=None,
            bbox_max=None,
            max_scale_exp=None,
            min_opacity_raw=-5.0,  # Low opacity points have -15.0
        )
        res = run_stage1_filter(self.data, config)
        self.assertEqual(res.stats["opacity_culled"], 8)

    def test_combined_stage1_pipeline(self):
        config = Stage1Config(
            remove_nan_inf=True,
            bbox_min=[-2.0, -2.0, -2.0],
            bbox_max=[2.0, 2.0, 2.0],
            max_scale_exp=5.0,
            min_opacity_raw=-5.0,
        )
        res = run_stage1_filter(self.data, config)
        # All 5 NaNs, 10 bbox outliers, 4 scale outliers, and 8 low-opacity points should be culled
        # Leaving precisely the 100 valid points!
        self.assertEqual(res.stats["surviving_count"], 100)
        self.assertEqual(res.stats["nan_inf_culled"], 5)
        self.assertEqual(res.stats["bbox_culled"], 10)
        self.assertEqual(res.stats["scale_culled"], 4)
        self.assertEqual(res.stats["opacity_culled"], 8)


if __name__ == "__main__":
    unittest.main()
