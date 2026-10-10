import json
import random
from pathlib import Path

from core.config import (
    GRID_LAT_MAX,
    GRID_LAT_MIN,
    GRID_LON_MAX,
    GRID_LON_MIN,
    GRID_STEP,
    HORIZON_HOURS,
    WIND_INTERVAL_HOURS,
)
from core.models import Fire, Site, Wind


def generate_fires(n: int = 50) -> list:
    fires = []
    for i in range(n):
        lat = random.uniform(29.5, 31.0)
        lon = random.uniform(74.5, 76.5)
        frp = random.uniform(10, 100)
        confidence = random.randint(70, 100)
        fires.append(Fire(lat=lat, lon=lon, frp=frp, confidence=confidence))
    return fires


def generate_wind_grid() -> list:
    winds = []
    n_steps = HORIZON_HOURS // WIND_INTERVAL_HOURS + 1
    for step in range(n_steps):
        winds.append(Wind(speed_kmh=12.0, dir_deg=270.0, blh_m=800.0))
    return winds


def generate_sites() -> list:
    sites = [
        Site(
            id="s1", name="Govt School Dwarka", lat=28.5921, lon=77.0460, type="school"
        ),
        Site(
            id="s2", name="Govt School Rohini", lat=28.7041, lon=77.1025, type="school"
        ),
        Site(
            id="s3", name="Govt School Gurgaon", lat=28.4595, lon=77.0266, type="school"
        ),
        Site(
            id="s4", name="Govt School Noida", lat=28.5355, lon=77.3910, type="school"
        ),
        Site(
            id="s5",
            name="Govt School Faridabad",
            lat=28.4089,
            lon=77.3178,
            type="school",
        ),
        Site(
            id="h1",
            name="AIIMS Trauma Centre",
            lat=28.5672,
            lon=77.2100,
            type="hospital",
        ),
        Site(
            id="h2",
            name="Safdarjung Hospital",
            lat=28.5623,
            lon=77.2095,
            type="hospital",
        ),
        Site(
            id="h3", name="Medanta Gurgaon", lat=28.4479, lon=77.0543, type="hospital"
        ),
        Site(id="h4", name="Fortis Noida", lat=28.5497, lon=77.3335, type="hospital"),
        Site(
            id="h5",
            name="Asian Hospital Faridabad",
            lat=28.4312,
            lon=77.2987,
            type="hospital",
        ),
    ]
    return sites


def generate_grid_cells() -> list:
    cells = []
    lat = GRID_LAT_MIN
    while lat <= GRID_LAT_MAX:
        lon = GRID_LON_MIN
        while lon <= GRID_LON_MAX:
            cells.append({"lat": round(lat, 2), "lon": round(lon, 2)})
            lon += GRID_STEP
        lat += GRID_STEP
    return cells


def main():
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    fires = generate_fires(50)
    winds = generate_wind_grid()
    sites = generate_sites()
    grid = generate_grid_cells()

    with open(data_dir / "mock_fires.json", "w") as f:
        json.dump([fire.model_dump() for fire in fires], f, indent=2)

    with open(data_dir / "mock_wind.json", "w") as f:
        json.dump([wind.model_dump() for wind in winds], f, indent=2)

    with open(data_dir / "mock_sites.json", "w") as f:
        json.dump([site.model_dump() for site in sites], f, indent=2)

    with open(data_dir / "mock_grid.json", "w") as f:
        json.dump(grid, f, indent=2)

    print(
        f"Generated: {len(fires)} fires, {len(winds)} wind steps, {len(sites)} sites, {len(grid)} grid cells"
    )


if __name__ == "__main__":
    main()
