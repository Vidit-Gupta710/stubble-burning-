"""
NASA FIRMS API Client - fetches fire hotspots for Punjab/Haryana/Delhi-NCR
"""
import os
import csv
import requests
from io import StringIO
from typing import List
from datetime import datetime, timedelta
from pathlib import Path

from core.models import Fire
from core.config import GRID_LAT_MIN, GRID_LAT_MAX, GRID_LON_MIN, GRID_LON_MAX


FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "cd5d20415e3dca1283b1811765b32d09")
DEFAULT_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
DEFAULT_BBOX = "74,28,78,31.5"  # Punjab, Haryana, Delhi-NCR
DEFAULT_DAY_RANGE = 1
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def build_firms_url(
    map_key: str = DEFAULT_MAP_KEY,
    source: str = "VIIRS_SNPP_NRT",
    bbox: str = DEFAULT_BBOX,
    day_range: int = DEFAULT_DAY_RANGE,
    date: str = None,
) -> str:
    if date is None:
        date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{FIRMS_BASE_URL}/{map_key}/{source}/{bbox}/{day_range}/{date}"


FIRMS_API_KEY = os.getenv("FIRMS_API_KEY", "723f4dc04f8e7f0664f92f8aa6baf2dd44b505632fcdb4fece2bef0af9994038")


def fetch_firms_csv(url: str) -> str:
    headers = {"X-API-Key": FIRMS_API_KEY} if FIRMS_API_KEY else {}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_firms_csv(csv_text: str) -> List[Fire]:
    fires = []
    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            
            # Filter to our region of interest
            if not (GRID_LAT_MIN <= lat <= GRID_LAT_MAX and GRID_LON_MIN <= lon <= GRID_LON_MAX):
                continue
            
            frp = float(row.get("frp", 0) or 0)
            conf_raw = row.get("confidence", "0")
            # Handle confidence: "n" (nominal), "h" (high), "l" (low), or numeric
            if conf_raw in ("n", "h"):
                confidence = 80
            elif conf_raw == "l":
                confidence = 30
            else:
                confidence = int(float(conf_raw))
            
            if frp > 0 and confidence >= 30:
                fires.append(Fire(lat=lat, lon=lon, frp=frp, confidence=confidence))
        except (ValueError, KeyError):
            continue
    return fires


def fetch_fires(
    date: str = None,
    sources: List[str] = None,
    map_key: str = None,
) -> List[Fire]:
    if sources is None:
        sources = DEFAULT_SOURCES
    if map_key is None:
        map_key = DEFAULT_MAP_KEY
    
    all_fires = []
    for source in sources:
        url = build_firms_url(map_key=map_key, source=source, date=date)
        try:
            csv_text = fetch_firms_csv(url)
            fires = parse_firms_csv(csv_text)
            all_fires.extend(fires)
            print(f"  {source}: {len(fires)} fires")
        except requests.RequestException as e:
            print(f"  {source} failed: {e}")
    
    # Deduplicate by location (within ~1km)
    unique_fires = []
    for fire in all_fires:
        is_dup = False
        for uf in unique_fires:
            if abs(fire.lat - uf.lat) < 0.01 and abs(fire.lon - uf.lon) < 0.01:
                is_dup = True
                if fire.frp > uf.frp:
                    uf.frp = fire.frp
                    uf.confidence = max(uf.confidence, fire.confidence)
                break
        if not is_dup:
            unique_fires.append(fire)
    
    return unique_fires


def save_raw_csv(csv_text: str, source: str, date: str):
    filepath = DATA_DIR / f"firms_{source}_{date}.csv"
    filepath.write_text(csv_text)
    print(f"  Saved raw CSV: {filepath}")


def main():
    date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching FIRMS data for {date}...")
    
    all_fires = []
    for source in DEFAULT_SOURCES:
        url = build_firms_url(source=source, date=date)
        try:
            csv_text = fetch_firms_csv(url)
            save_raw_csv(csv_text, source, date)
            fires = parse_firms_csv(csv_text)
            all_fires.extend(fires)
            print(f"  {source}: {len(fires)} fires in region")
        except Exception as e:
            print(f"  {source} error: {e}")
    
    # Deduplicate
    unique = []
    for fire in all_fires:
        dup = False
        for u in unique:
            if abs(fire.lat - u.lat) < 0.01 and abs(fire.lon - u.lon) < 0.01:
                dup = True
                if fire.frp > u.frp:
                    u.frp = fire.frp
                    u.confidence = max(u.confidence, fire.confidence)
                break
        if not dup:
            unique.append(fire)
    
    # Save to mock_fires.json format for compatibility
    import json
    out_path = DATA_DIR / "mock_fires.json"
    out_path.write_text(json.dumps([f.model_dump() for f in unique], indent=2))
    print(f"\nTotal unique fires: {len(unique)}")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()