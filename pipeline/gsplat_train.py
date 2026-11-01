"""Runs gsplat's examples/simple_trainer.py with Windows-friendly data loading.

simple_trainer.py hard-codes `num_workers=4` for its training DataLoader. On Windows every
worker is a separate process that loads its own copy of PyTorch's CUDA libraries (~1.7 GB of
committed memory each), which exhausted memory on a 16 GB laptop ("The paging file is too
small"). This wrapper caps the worker count before running the trainer unchanged.

Usage (all arguments after the trainer path are passed through):
    python pipeline/gsplat_train.py <gsplat>/examples/simple_trainer.py mcmc --data-dir ... [...]

Set NAMMA_GSPLAT_WORKERS to change the cap (default 0 on Windows = load in the main process,
2 elsewhere).
"""

import os
import runpy
import sys
from pathlib import Path

import torch.utils.data

default_workers = "0" if sys.platform == "win32" else "2"
MAX_WORKERS = int(os.environ.get("NAMMA_GSPLAT_WORKERS", default_workers))

_OriginalDataLoader = torch.utils.data.DataLoader


class CappedDataLoader(_OriginalDataLoader):
    def __init__(self, *args, **kwargs):
        workers = min(kwargs.get("num_workers", 0), MAX_WORKERS)
        kwargs["num_workers"] = workers
        if workers == 0:
            # These options are only valid with worker processes
            kwargs.pop("persistent_workers", None)
            kwargs.pop("prefetch_factor", None)
        super().__init__(*args, **kwargs)


torch.utils.data.DataLoader = CappedDataLoader

if len(sys.argv) < 2:
    sys.exit(__doc__)

trainer = Path(sys.argv[1]).resolve()
# The trainer imports its sibling modules (datasets/, utils.py) relative to its own folder
sys.path.insert(0, str(trainer.parent))
os.chdir(trainer.parent)
sys.argv = [str(trainer), *sys.argv[2:]]
print(f"[gsplat_train] DataLoader workers capped at {MAX_WORKERS}", flush=True)
runpy.run_path(str(trainer), run_name="__main__")
