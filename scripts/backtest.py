"""
Backtest script: compares exposure scores against observed PM2.5 at stations
Uses mock historical data for demo purposes.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.config import THRESHOLDS
from core.exposure import compute_exposure
from core.models import Fire, GridCell, Site, Wind


@dataclass
class HistoricalDay:
    date: str
    fires: list[Fire]
    winds: list[Wind]
    stations: list[Site]
    observed_pm25: dict  # station_id -> pm25 value


def generate_historical_data(n_days: int = 15) -> list[HistoricalDay]:
    """Generate mock historical data for backtesting."""
    random.seed(42)
    np.random.seed(42)

    days = []

    for day_idx in range(n_days):
        date = f"2024-10-{15 + day_idx:02d}"

        # Generate fires - more fires on some days
        n_fires = random.randint(20, 80)
        fires = []
        for _ in range(n_fires):
            lat = random.uniform(29.5, 31.0)
            lon = random.uniform(74.5, 76.5)
            frp = random.uniform(10, 100)
            confidence = random.randint(70, 100)
            fires.append(Fire(lat=lat, lon=lon, frp=frp, confidence=confidence))

        # Generate wind - varying direction and speed
        wind_dir = random.choice(
            [270, 250, 290, 310, 90]
        )  # Mostly westerly, some easterly
        wind_speed = random.uniform(5, 20)
        blh = random.uniform(500, 1500)

        winds = []
        for step in range(17):  # 48h / 3h = 16 steps + 1
            # Add some variation
            dir_var = wind_dir + random.uniform(-20, 20)
            speed_var = max(1, wind_speed + random.uniform(-3, 3))
            blh_var = max(200, blh + random.uniform(-200, 200))
            winds.append(
                Wind(speed_kmh=speed_var, dir_deg=dir_var % 360, blh_m=blh_var)
            )

        # Stations in Delhi-NCR
        stations = [
            Site(
                id="stn1",
                name="Delhi Anand Vihar",
                lat=28.65,
                lon=77.31,
                type="station",
            ),
            Site(
                id="stn2", name="Delhi RK Puram", lat=28.57, lon=77.17, type="station"
            ),
            Site(id="stn3", name="Gurugram", lat=28.46, lon=77.03, type="station"),
            Site(id="stn4", name="Noida", lat=28.54, lon=77.33, type="station"),
            Site(id="stn5", name="Faridabad", lat=28.41, lon=77.32, type="station"),
        ]

        # Observed PM2.5 - higher when fires upwind
        grid = [GridCell(lat=s.lat, lon=s.lon) for s in stations]
        results = compute_exposure(fires, winds, grid, hour_idx=0)

        observed_pm25 = {}
        for i, stn in enumerate(stations):
            exposure = results[i].cell.score
            # PM2.5 correlates with exposure but with noise
            base_pm25 = 50 + exposure * 0.08 + random.uniform(-20, 30)
            observed_pm25[stn.id] = max(15, base_pm25)

        days.append(
            HistoricalDay(
                date=date,
                fires=fires,
                winds=winds,
                stations=stations,
                observed_pm25=observed_pm25,
            )
        )

    return days


def run_backtest(days: list[HistoricalDay]) -> dict:
    """Run backtest: compute exposure at stations, correlate with observed PM2.5 at lags 0-48h."""

    # Build grid for stations
    all_stations = days[0].stations
    grid = [GridCell(lat=s.lat, lon=s.lon) for s in all_stations]

    results_by_lag = {lag: [] for lag in range(0, 49, 3)}  # Every 3 hours

    for day in days:
        for lag_hours in range(0, 49, 3):
            hour_idx = lag_hours // 3
            if hour_idx >= len(day.winds):
                continue

            results = compute_exposure(day.fires, day.winds, grid, hour_idx=hour_idx)

            for i, stn in enumerate(all_stations):
                exposure = results[i].cell.score
                observed = day.observed_pm25[stn.id]
                results_by_lag[lag_hours].append(
                    (exposure, observed, day.date, stn.name)
                )

    # Compute correlations
    correlations = {}
    for lag, pairs in results_by_lag.items():
        if len(pairs) < 3:
            correlations[lag] = None
            continue
        exposures = [p[0] for p in pairs]
        observed = [p[1] for p in pairs]
        corr = np.corrcoef(exposures, observed)[0, 1]
        correlations[lag] = corr

    return {
        "correlations": correlations,
        "raw_pairs": results_by_lag,
    }


def print_backtest_results(backtest: dict):
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    console.print(Panel.fit("[bold cyan]BACKTEST RESULTS[/bold cyan]"))

    console.print("\n[bold]Correlation by Lag (Exposure vs Observed PM2.5)[/bold]")
    corr_table = Table()
    corr_table.add_column("Lag (hours)")
    corr_table.add_column("Correlation")
    corr_table.add_column("Interpretation")

    for lag in sorted(backtest["correlations"].keys()):
        corr = backtest["correlations"][lag]
        if corr is None:
            corr_table.add_row(f"{lag}h", "N/A", "Insufficient data")
        else:
            interp = (
                "Strong"
                if corr > 0.7
                else "Moderate"
                if corr > 0.4
                else "Weak"
                if corr > 0.2
                else "None"
            )
            corr_table.add_row(f"{lag}h", f"{corr:.3f}", interp)

    console.print(corr_table)

    # Find best lag
    valid_corrs = {k: v for k, v in backtest["correlations"].items() if v is not None}
    if valid_corrs:
        best_lag = max(valid_corrs, key=lambda k: valid_corrs[k])
        best_corr = valid_corrs[best_lag]
        console.print(
            f"\n[green]Best correlation: {best_corr:.3f} at {best_lag}h lag[/green]"
        )

        # Suggest thresholds based on backtest
        console.print("\n[bold]Suggested Threshold Calibration[/bold]")
        threshold_table = Table()
        threshold_table.add_column("Tier")
        threshold_table.add_column("Current")
        threshold_table.add_column("Suggested")
        threshold_table.add_column("Rationale")

        # Simple heuristic: set WARNING at ~75th percentile of exposure when PM2.5 > 100
        high_pm_pairs = []
        for lag, pairs in backtest["raw_pairs"].items():
            for exp, obs, _, _ in pairs:
                if obs > 100:  # Poor AQI
                    high_pm_pairs.append(exp)

        if high_pm_pairs:
            p75 = np.percentile(high_pm_pairs, 75)
            p90 = np.percentile(high_pm_pairs, 90)
            threshold_table.add_row(
                "WATCH",
                str(THRESHOLDS["WATCH"]),
                f"{p75:.0f}",
                "75th percentile on high PM days",
            )
            threshold_table.add_row(
                "WARNING",
                str(THRESHOLDS["WARNING"]),
                f"{p75:.0f}",
                "75th percentile on high PM days",
            )
            threshold_table.add_row(
                "EMERGENCY",
                str(THRESHOLDS["EMERGENCY"]),
                f"{p90:.0f}",
                "90th percentile on high PM days",
            )
        else:
            threshold_table.add_row("WATCH", str(THRESHOLDS["WATCH"]), "100", "Default")
            threshold_table.add_row(
                "WARNING", str(THRESHOLDS["WARNING"]), "500", "Default"
            )
            threshold_table.add_row(
                "EMERGENCY", str(THRESHOLDS["EMERGENCY"]), "1500", "Default"
            )

        console.print(threshold_table)

    # Lead time analysis
    console.print("\n[bold]Lead Time Analysis[/bold]")
    lead_table = Table()
    lead_table.add_column("Lag (h)")
    lead_table.add_column("Mean Exposure (High PM2.5)")
    lead_table.add_column("Mean Exposure (Low PM2.5)")
    lead_table.add_column("Separation")

    for lag in sorted(backtest["raw_pairs"].keys()):
        pairs = backtest["raw_pairs"][lag]
        high_exp = [p[0] for p in pairs if p[1] > 100]
        low_exp = [p[0] for p in pairs if p[1] <= 100]
        if high_exp and low_exp:
            mean_high = np.mean(high_exp)
            mean_low = np.mean(low_exp)
            sep = mean_high - mean_low
            lead_table.add_row(
                f"{lag}h", f"{mean_high:.1f}", f"{mean_low:.1f}", f"{sep:.1f}"
            )

    console.print(lead_table)


def main():
    print("Generating mock historical data...")
    days = generate_historical_data(15)
    print(f"Generated {len(days)} days of historical data")

    print("Running backtest...")
    backtest = run_backtest(days)

    print_backtest_results(backtest)

    # Save results
    output = {
        "correlations": {str(k): v for k, v in backtest["correlations"].items()},
        "best_lag_hours": max(
            {k: v for k, v in backtest["correlations"].items() if v is not None},
            key=lambda k: {
                k: v for k, v in backtest["correlations"].items() if v is not None
            }[k],
        )
        if any(v is not None for v in backtest["correlations"].values())
        else 0,
    }

    out_path = Path(__file__).parent.parent / "backtest_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
