"""
OpenAQ v3 API Client - fetches PM2.5 data for stations in Punjab/Haryana/Delhi-NCR
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from core.config import GRID_LAT_MAX, GRID_LAT_MIN, GRID_LON_MAX, GRID_LON_MIN
from core.models import Site

OPENAQ_BASE_URL = "https://api.openaq.org/v3"
OPENAQ_API_KEY = os.getenv(
    "OPENAQ_API_KEY", "723f4dc04f8e7f0664f92f8aa6baf2dd44b505632fcdb4fece2bef0af9994038"
)
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# Known stations in Delhi-NCR region
DELHI_NCR_STATIONS = [
    {"id": "stn1", "name": "Delhi Anand Vihar", "lat": 28.65, "lon": 77.31},
    {"id": "stn2", "name": "Delhi RK Puram", "lat": 28.57, "lon": 77.17},
    {"id": "stn3", "name": "Gurugram", "lat": 28.46, "lon": 77.03},
    {"id": "stn4", "name": "Noida", "lat": 28.54, "lon": 77.33},
    {"id": "stn5", "name": "Faridabad", "lat": 28.41, "lon": 77.32},
    {"id": "stn6", "name": "Delhi Punjabi Bagh", "lat": 28.67, "lon": 77.13},
    {"id": "stn7", "name": "Delhi Dwarka", "lat": 28.59, "lon": 77.05},
    {"id": "stn8", "name": "Ghaziabad", "lat": 28.67, "lon": 77.45},
]


def get_headers() -> dict:
    return {"X-API-Key": OPENAQ_API_KEY} if OPENAQ_API_KEY else {}


def fetch_stations() -> list[Site]:
    """Get all stations in the region."""
    url = f"{OPENAQ_BASE_URL}/locations"
    params = {
        "bbox": f"{GRID_LON_MIN},{GRID_LAT_MIN},{GRID_LON_MAX},{GRID_LAT_MAX}",
        "parameters": "pm25",
        "limit": 100,
    }
    response = requests.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    stations = []
    for loc in data.get("results", []):
        coords = loc.get("coordinates", {})
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if (
            lat
            and lon
            and GRID_LAT_MIN <= lat <= GRID_LAT_MAX
            and GRID_LON_MIN <= lon <= GRID_LON_MAX
        ):
            stations.append(
                Site(
                    id=f"openaq_{loc['id']}",
                    name=loc.get("name", f"Station {loc['id']}"),
                    lat=lat,
                    lon=lon,
                    type="station",
                )
            )
    return stations


def fetch_pm25_series(
    station_id: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Fetch PM2.5 measurements for a station over a date range."""
    url = f"{OPENAQ_BASE_URL}/locations/{station_id}/measurements"
    params = {
        "parameter": "pm25",
        "date_from": start_date,
        "date_to": end_date,
        "limit": 10000,
    }
    response = requests.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    results = []
    for m in data.get("results", []):
        results.append(
            {
                "timestamp": m.get("period", {}).get("datetimeFrom", {}).get("utc"),
                "value": m.get("value"),
                "unit": m.get("unit"),
            }
        )
    return results


def fetch_latest_pm25(stations: list[Site]) -> dict[str, float]:
    """Get latest PM2.5 value for each station."""
    latest = {}
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")

    for station in stations:
        try:
            # Extract numeric ID from our station ID
            loc_id = station.id.replace("openaq_", "")
            series = fetch_pm25_series(loc_id, start, end)
            if series:
                # Get most recent valid measurement
                for m in reversed(series):
                    if m["value"] is not None:
                        latest[station.id] = float(m["value"])
                        break
        except Exception as e:
            print(f"  Failed to fetch {station.name}: {e}")
    return latest


def save_stations_json(stations: list[Site], filename: str = "openaq_stations.json"):
    import json

    filepath = DATA_DIR / filename
    filepath.write_text(json.dumps([s.model_dump() for s in stations], indent=2))
    print(f"Saved {len(stations)} stations to {filepath}")


def save_pm25_json(data: dict, filename: str = "openaq_pm25.json"):
    import json

    filepath = DATA_DIR / filename
    filepath.write_text(json.dumps(data, indent=2))
    print(f"Saved PM2.5 data to {filepath}")


def main():
    print("Fetching OpenAQ stations in Delhi-NCR region...")
    stations = fetch_stations()
    print(f"Found {len(stations)} stations with PM2.5")
    save_stations_json(stations)

    print("Fetching latest PM2.5 measurements...")
    pm25 = fetch_latest_pm25(stations)
    print(f"Got PM2.5 for {len(pm25)} stations")
    for sid, val in pm25.items():
        stn = next(s for s in stations if s.id == sid)
        print(f"  {stn.name}: {val} µg/m³")
    save_pm25_json(pm25)


if __name__ == "__main__":
    main()
