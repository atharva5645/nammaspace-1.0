"""Pure-PyTorch stand-in for the `fused-ssim` CUDA extension used by gsplat's trainer.

The real package must be compiled with the CUDA toolkit and MSVC, which this Windows
machine does not have. This version computes the same SSIM (11x11 Gaussian window,
sigma 1.5, standard C1/C2 constants) with ordinary convolutions. It is slower per step
than the fused kernel but gives the same loss, so training quality is unchanged.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

__all__ = ["fused_ssim"]

_WINDOW = 11
_SIGMA = 1.5
_C1 = 0.01 ** 2
_C2 = 0.03 ** 2
_kernel_cache: dict[tuple, torch.Tensor] = {}


def _gaussian_kernel(channels: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    key = (channels, device, dtype)
    kernel = _kernel_cache.get(key)
    if kernel is None:
        coords = torch.arange(_WINDOW, device=device, dtype=dtype) - _WINDOW // 2
        g = torch.exp(-(coords ** 2) / (2 * _SIGMA ** 2))
        g = g / g.sum()
        kernel = (g[:, None] @ g[None, :]).expand(channels, 1, _WINDOW, _WINDOW).contiguous()
        _kernel_cache[key] = kernel
    return kernel


def fused_ssim(img1: torch.Tensor, img2: torch.Tensor, padding: str = "same", train: bool = True) -> torch.Tensor:
    """Mean SSIM between two (N, C, H, W) image batches in [0, 1].

    padding="same" keeps the full image (zero-padded borders); "valid" ignores the
    5-pixel border, matching the fused-ssim package. `train` is accepted for API
    compatibility and has no effect.
    """
    if padding not in ("same", "valid"):
        raise ValueError(f"padding must be 'same' or 'valid', got {padding!r}")
    channels = img1.shape[1]
    kernel = _gaussian_kernel(channels, img1.device, img1.dtype)
    pad = _WINDOW // 2 if padding == "same" else 0

    def blur(x: torch.Tensor) -> torch.Tensor:
        return F.conv2d(x, kernel, padding=pad, groups=channels)

    mu1, mu2 = blur(img1), blur(img2)
    mu1_sq, mu2_sq, mu12 = mu1 * mu1, mu2 * mu2, mu1 * mu2
    sigma1_sq = blur(img1 * img1) - mu1_sq
    sigma2_sq = blur(img2 * img2) - mu2_sq
    sigma12 = blur(img1 * img2) - mu12

    ssim_map = ((2 * mu12 + _C1) * (2 * sigma12 + _C2)) / ((mu1_sq + mu2_sq + _C1) * (sigma1_sq + sigma2_sq + _C2))
    return ssim_map.mean()
