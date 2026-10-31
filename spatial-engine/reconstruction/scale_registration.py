"""Metric scale registration from measured spans with reconstructed endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Literal

Vec3 = tuple[float, float, float]
Units = Literal["m", "cm", "ft", "in"]
TO_METERS: dict[Units, float] = {"m": 1.0, "cm": 0.01, "ft": 0.3048, "in": 0.0254}


@dataclass(frozen=True)
class ScaleAnchor:
    id: str
    start: Vec3
    end: Vec3
    measured_distance: float
    units: Units
    tolerance: float
    weight: float = 1.0
    source: str = "tape"


@dataclass(frozen=True)
class ScaleRegistration:
    status: Literal["accepted", "held"]
    units: Literal["m"]
    meters_per_reconstruction_unit: float
    weighted_rms_residual_m: float
    anchors: list[dict]
    transform: list[list[float]]
    authority: Literal[False] = False


def _distance(a: Vec3, b: Vec3) -> float:
    if len(a) != 3 or len(b) != 3 or not all(isfinite(value) for value in (*a, *b)):
        raise ValueError("Scale anchors require finite 3D endpoint coordinates")
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def register_metric_scale(anchors: list[ScaleAnchor]) -> ScaleRegistration:
    """Fit one uniform meters-per-unit scale and hold if anchors disagree.

    The caller must supply reconstructed 3D endpoints corresponding to measured
    physical endpoints. This routine cannot find those correspondences in photos.
    It deliberately grants no measurement authority; independent QA remains
    required before publishing a dimensionally validated model.
    """
    if not anchors:
        raise ValueError("At least one measured anchor correspondence is required")
    scales: list[float] = []
    weights: list[float] = []
    source_distances: list[float] = []
    measured_meters: list[float] = []
    for anchor in anchors:
        if anchor.units not in TO_METERS:
            raise ValueError(f"Unsupported scale unit: {anchor.units}")
        if not isfinite(anchor.measured_distance) or anchor.measured_distance <= 0:
            raise ValueError(f"Anchor {anchor.id!r} must have a positive measured distance")
        if not isfinite(anchor.tolerance) or anchor.tolerance < 0 or not isfinite(anchor.weight) or anchor.weight <= 0:
            raise ValueError(f"Anchor {anchor.id!r} has invalid tolerance or weight")
        source_distance = _distance(anchor.start, anchor.end)
        if source_distance <= 1e-9:
            raise ValueError(f"Anchor {anchor.id!r} has coincident reconstructed endpoints")
        target_meters = anchor.measured_distance * TO_METERS[anchor.units]
        source_distances.append(source_distance)
        measured_meters.append(target_meters)
        scales.append(target_meters / source_distance)
        weights.append(anchor.weight)

    scale = sum(weight * distance * measured for weight, distance, measured in zip(weights, source_distances, measured_meters)) / sum(
        weight * distance * distance for weight, distance in zip(weights, source_distances)
    )
    results = []
    weighted_error_sum = 0.0
    all_within_tolerance = True
    for anchor, source_distance, measured, weight in zip(anchors, source_distances, measured_meters, weights):
        fitted = source_distance * scale
        residual = fitted - measured
        tolerance_m = anchor.tolerance * TO_METERS[anchor.units]
        weighted_error_sum += weight * residual * residual
        within = abs(residual) <= tolerance_m
        all_within_tolerance = all_within_tolerance and within
        results.append({
            "id": anchor.id,
            "source": anchor.source,
            "measuredMeters": measured,
            "fittedMeters": fitted,
            "residualMeters": residual,
            "toleranceMeters": tolerance_m,
            "weight": weight,
            "satisfied": within,
        })
    rms = sqrt(weighted_error_sum / sum(weights))
    return ScaleRegistration(
        status="accepted" if all_within_tolerance else "held",
        units="m",
        meters_per_reconstruction_unit=scale,
        weighted_rms_residual_m=rms,
        anchors=results,
        transform=[
            [scale, 0.0, 0.0, 0.0],
            [0.0, scale, 0.0, 0.0],
            [0.0, 0.0, scale, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )
