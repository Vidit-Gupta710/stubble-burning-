# Stubble Burning Early Warning - Demo

A compressed 3-hour demo of the smoke exposure prediction system for Punjab/Haryana/Delhi-NCR.

## Quick Start

```bash
pip install -r requirements.txt
python -m scripts.run_demo
```

## What It Does

1. **Loads mock data**: 50 fire hotspots in Punjab/Haryana, 48h wind forecast, 10 seeded sites (schools/hospitals) in Delhi-NCR
2. **Computes exposure**: Vectorized numpy engine scores each 0.1° grid cell using:
   - Fire radiative power (FRP) and confidence
   - Wind direction/speed and boundary layer height
   - Gaussian kernels for direction, distance, and mixing effects
3. **Generates alerts**: Sites with tier ≥ WARNING get actionable alerts with lead time estimates

## Output Example

```
🔥 FIRE CLUSTERS (top 5 by total FRP)
  1. 30.26, 75.65: 5 fires, 284 MW

💨 WIND (t=0h): 270° @ 12 km/h, BLH 800m

🎯 TOP 10 EXPOSURE GRID CELLS
  1. 29.40, 78.00: 2065 → EMERGENCY

🚨 ALERTS (sites with tier ≥ WARNING)
  WARNING | Govt School Noida     | Move sports indoors tomorrow | ~13h
  WARNING | AIIMS Trauma Centre   | Move sports indoors tomorrow | ~12h
  ...
```

## Project Structure

```
stubble/
├── core/
│   ├── config.py      # Model constants (sigma, a, b, thresholds)
│   ├── models.py      # Pydantic models (Fire, Wind, GridCell, Site, etc.)
│   └── exposure.py    # Vectorized numpy exposure engine
├── scripts/
│   ├── generate_mock.py  # Creates mock data in data/
│   └── run_demo.py       # Main demo entry point
├── data/
│   ├── mock_fires.json
│   ├── mock_wind.json
│   ├── mock_sites.json
│   └── mock_grid.json
├── tests/
│   └── test_exposure.py  # 4 tests (upwind, downwind, calm wind, performance)
├── requirements.txt
└── README.md
```

## Tests

```bash
pytest -q
# 4 passed in ~0.3s
```

## Model Parameters (config.py)

| Parameter | Value | Description |
|-----------|-------|-------------|
| SIGMA_DEG | 25.0 | Directional spread (degrees) |
| A | 0.5 | Low BLH amplification factor |
| B | 0.3 | Low wind speed amplification factor |
| THRESHOLDS | WATCH=100, WARNING=500, EMERGENCY=1500 | Tier cutoffs |

## Notes

- **No AWS infrastructure** - pure Python demo for hackathon time constraints
- **No live APIs** - uses committed mock data for reproducibility
- **English only** - alert messages in English (no Hindi/Punjabi)
- **Performance**: 2000 fires × 256 cells in <0.1s (well under 3s target)