import numpy as np

from core.config import (
    BLH_REF,
    HORIZON_HOURS,
    REACH_FACTOR,
    REACH_OFFSET,
    REACH_SPREAD,
    SIGMA_DEG,
    WS_REF,
    A,
    B,
)
from core.models import ExposureResult, Fire, GridCell, Wind, tier_from_score


def haversine_km(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    R = 6371.0
    lat1_r = np.deg2rad(lat1)
    lon1_r = np.deg2rad(lon1)
    lat2_r = np.deg2rad(lat2)
    lon2_r = np.deg2rad(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def bearing_deg(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    lat1_r = np.deg2rad(lat1)
    lon1_r = np.deg2rad(lon1)
    lat2_r = np.deg2rad(lat2)
    lon2_r = np.deg2rad(lon2)
    dlon = lon2_r - lon1_r
    y = np.sin(dlon) * np.cos(lat2_r)
    x = np.cos(lat1_r) * np.sin(lat2_r) - np.sin(lat1_r) * np.cos(lat2_r) * np.cos(dlon)
    brng = np.rad2deg(np.arctan2(y, x))
    return (brng + 360) % 360


def angular_diff_deg(bearing: np.ndarray, wind_to: np.ndarray) -> np.ndarray:
    diff = np.abs(bearing - wind_to) % 360
    return np.minimum(diff, 360 - diff)


def compute_exposure(
    fires: list[Fire],
    winds: list[Wind],
    grid_cells: list[GridCell],
    hour_idx: int = 0,
) -> list[ExposureResult]:
    if not fires or not grid_cells:
        return [ExposureResult(cell=cell) for cell in grid_cells]

    len(fires)
    len(grid_cells)

    fire_lats = np.array([f.lat for f in fires], dtype=np.float64)
    fire_lons = np.array([f.lon for f in fires], dtype=np.float64)
    fire_frp = np.array([f.frp for f in fires], dtype=np.float64)
    fire_conf = np.array([f.confidence / 100.0 for f in fires], dtype=np.float64)

    cell_lats = np.array([c.lat for c in grid_cells], dtype=np.float64)
    cell_lons = np.array([c.lon for c in grid_cells], dtype=np.float64)

    wind = winds[hour_idx] if hour_idx < len(winds) else winds[-1]
    wind_speed = wind.speed_kmh
    wind_dir = wind.dir_deg
    blh = wind.blh_m

    reach = wind_speed * HORIZON_HOURS

    fire_lats_2d = fire_lats[:, np.newaxis]
    fire_lons_2d = fire_lons[:, np.newaxis]
    cell_lats_2d = cell_lats[np.newaxis, :]
    cell_lons_2d = cell_lons[np.newaxis, :]

    d = haversine_km(fire_lats_2d, fire_lons_2d, cell_lats_2d, cell_lons_2d)

    bearing = bearing_deg(fire_lats_2d, fire_lons_2d, cell_lats_2d, cell_lons_2d)
    wind_to = (wind_dir + 180) % 360
    dtheta = angular_diff_deg(bearing, wind_to)

    K_dir = np.exp(-(dtheta**2) / (2 * SIGMA_DEG**2))

    peak_dist = REACH_FACTOR * reach
    spread = REACH_SPREAD * reach + REACH_OFFSET
    K_dist = np.exp(-((d - peak_dist) ** 2) / (2 * spread**2))

    blh_factor = 1 + A * (1 - np.minimum(blh, BLH_REF) / BLH_REF)
    ws_factor = 1 + B * (1 - np.minimum(wind_speed, WS_REF) / WS_REF)
    K_mix = blh_factor * ws_factor

    contrib = (
        fire_frp[:, np.newaxis] * fire_conf[:, np.newaxis] * K_dir * K_dist * K_mix
    )

    exposure_scores = contrib.sum(axis=0)

    results = []
    for i, cell in enumerate(grid_cells):
        cell_copy = GridCell(
            lat=cell.lat,
            lon=cell.lon,
            score=float(exposure_scores[i]),
            tier=tier_from_score(float(exposure_scores[i])),
        )
        top_fire_indices = np.argsort(contrib[:, i])[::-1][:5]
        contributing = [int(idx) for idx in top_fire_indices if contrib[idx, i] > 0]
        results.append(ExposureResult(cell=cell_copy, contributing_fires=contributing))

    return results
