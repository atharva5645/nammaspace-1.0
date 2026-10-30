import tempfile
import unittest
from pathlib import Path
import numpy as np

from pipeline.filter.ply_io import read_ply_gaussian, write_ply_gaussian
from pipeline.filter.synthetic import create_synthetic_3dgs_data


class TestPlyIO(unittest.TestCase):
    def test_write_and_read_roundtrip(self):
        data, counts = create_synthetic_3dgs_data(
            num_valid=50,
            num_nan=0,
            num_bbox_outliers=5,
            num_scale_outliers=0,
            num_low_opacity=0,
            seed=123,
        )
        total = counts["total"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_roundtrip.ply"
            write_ply_gaussian(test_file, data, comments=["Unit test roundtrip"])
            self.assertTrue(test_file.exists())
            self.assertGreater(test_file.stat().st_size, 0)

            loaded_data, header = read_ply_gaussian(test_file)
            self.assertEqual(len(loaded_data), total)
            self.assertEqual(header["format"], "binary_little_endian")

            # Check that float properties match within floating precision
            np.testing.assert_allclose(loaded_data["x"], data["x"], rtol=1e-5, atol=1e-5)
            np.testing.assert_allclose(loaded_data["y"], data["y"], rtol=1e-5, atol=1e-5)
            np.testing.assert_allclose(loaded_data["z"], data["z"], rtol=1e-5, atol=1e-5)
            np.testing.assert_allclose(loaded_data["opacity"], data["opacity"], rtol=1e-5, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
