from enum import Enum

from pydantic import BaseModel


class Tier(str, Enum):
    NONE = "NONE"
    WATCH = "WATCH"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class Fire(BaseModel):
    lat: float
    lon: float
    frp: float
    confidence: int


class Wind(BaseModel):
    speed_kmh: float
    dir_deg: float
    blh_m: float


class GridCell(BaseModel):
    lat: float
    lon: float
    score: float = 0.0
    tier: Tier = Tier.NONE


class Site(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    type: str


class ExposureResult(BaseModel):
    cell: GridCell
    contributing_fires: list[int] = []


def tier_from_score(score: float) -> Tier:
    from core.config import THRESHOLDS

    if score >= THRESHOLDS["EMERGENCY"]:
        return Tier.EMERGENCY
    if score >= THRESHOLDS["WARNING"]:
        return Tier.WARNING
    if score >= THRESHOLDS["WATCH"]:
        return Tier.WATCH
    return Tier.NONE
