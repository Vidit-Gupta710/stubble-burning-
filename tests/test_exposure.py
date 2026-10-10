import numpy as np

from core.exposure import compute_exposure
from core.models import Fire, GridCell, Wind


def test_upwind_high_score():
    fires = [Fire(lat=29.0, lon=75.0, frp=500.0, confidence=100)]
    winds = [Wind(speed_kmh=15.0, dir_deg=270.0, blh_m=800.0)]
    grid = [GridCell(lat=28.5, lon=76.0)]
    results = compute_exposure(fires, winds, grid, hour_idx=0)
    assert results[0].cell.score > 100, (
        f"Expected high score for upwind, got {results[0].cell.score}"
    )
    assert results[0].cell.tier.value in ("WATCH", "WARNING", "EMERGENCY")


def test_downwind_near_zero():
    fires = [Fire(lat=29.0, lon=75.0, frp=100.0, confidence=100)]
    winds = [Wind(speed_kmh=10.0, dir_deg=90.0, blh_m=1000.0)]
    grid = [GridCell(lat=28.5, lon=76.0)]
    results = compute_exposure(fires, winds, grid, hour_idx=0)
    assert results[0].cell.score < 50, (
        f"Expected near-zero score for downwind, got {results[0].cell.score}"
    )
    assert results[0].cell.tier.value == "NONE"


def test_calm_low_blh_raises_score():
    fires = [Fire(lat=29.0, lon=75.0, frp=50.0, confidence=100)]
    winds_calm = [Wind(speed_kmh=2.0, dir_deg=270.0, blh_m=500.0)]
    winds_windy = [Wind(speed_kmh=15.0, dir_deg=270.0, blh_m=2000.0)]
    grid = [GridCell(lat=28.5, lon=76.0)]
    results_calm = compute_exposure(fires, winds_calm, grid, hour_idx=0)
    results_windy = compute_exposure(fires, winds_windy, grid, hour_idx=0)
    assert results_calm[0].cell.score > results_windy[0].cell.score, (
        f"Calm+low BLH should raise score: calm={results_calm[0].cell.score}, windy={results_windy[0].cell.score}"
    )


def test_vectorized_performance():
    import time

    fires = [
        Fire(
            lat=29.0 + np.random.uniform(-1, 1),
            lon=75.0 + np.random.uniform(-1, 1),
            frp=50.0,
            confidence=80,
        )
        for _ in range(2000)
    ]
    winds = [Wind(speed_kmh=12.0, dir_deg=270.0, blh_m=800.0)]
    grid = [
        GridCell(lat=28.0 + i * 0.1, lon=76.5 + j * 0.1)
        for i in range(16)
        for j in range(16)
    ]
    start = time.time()
    compute_exposure(fires, winds, grid, hour_idx=0)
    elapsed = time.time() - start
    assert elapsed < 3.0, f"Performance test failed: {elapsed:.2f}s > 3s"
