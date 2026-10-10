import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.exposure import compute_exposure
from core.models import Fire, GridCell, Site, Wind

console = Console()


@dataclass
class SiteForecast:
    site_id: str
    site_name: str
    site_type: str
    lat: float
    lon: float
    hourly_scores: list[float]
    hourly_tiers: list[str]
    lead_hours: list[float]


@dataclass
class ImpactCounters:
    population_exposed: int
    sites_alerted: int
    schools_alerted: int
    hospitals_alerted: int
    avg_lead_hours: float
    max_score: float


def load_mock_data():
    data_dir = Path(__file__).parent.parent / "data"
    with open(data_dir / "mock_fires.json") as f:
        fires = [Fire(**d) for d in json.load(f)]
    with open(data_dir / "mock_wind.json") as f:
        winds = [Wind(**d) for d in json.load(f)]
    with open(data_dir / "mock_sites.json") as f:
        sites = [Site(**d) for d in json.load(f)]
    with open(data_dir / "mock_grid.json") as f:
        grid = [GridCell(lat=d["lat"], lon=d["lon"]) for d in json.load(f)]
    return fires, winds, sites, grid


def cluster_fires(fires: list[Fire], radius_km: float = 25.0) -> list[dict]:
    import numpy as np

    from core.exposure import haversine_km

    if not fires:
        return []

    fire_lats = np.array([f.lat for f in fires])
    fire_lons = np.array([f.lon for f in fires])
    fire_frp = np.array([f.frp for f in fires])

    clusters = []
    used = np.zeros(len(fires), dtype=bool)

    for i in range(len(fires)):
        if used[i]:
            continue
        dists = haversine_km(fire_lats[i], fire_lons[i], fire_lats, fire_lons)
        cluster_idx = np.where((dists <= radius_km) & ~used)[0]
        used[cluster_idx] = True
        cluster_frp = fire_frp[cluster_idx].sum()
        cluster_max_frp = fire_frp[cluster_idx].max()
        center_lat = fire_lats[cluster_idx].mean()
        center_lon = fire_lons[cluster_idx].mean()
        clusters.append(
            {
                "center_lat": center_lat,
                "center_lon": center_lon,
                "count": len(cluster_idx),
                "total_frp": cluster_frp,
                "max_frp": cluster_max_frp,
            }
        )

    clusters.sort(key=lambda c: c["total_frp"], reverse=True)
    return clusters


def format_tier(tier: str) -> str:
    return tier


def estimate_lead_hours(site: Site, fires: list[Fire], wind: Wind) -> float:
    import numpy as np

    from core.exposure import haversine_km

    if not fires:
        return 0.0

    fire_lats = np.array([f.lat for f in fires])
    fire_lons = np.array([f.lon for f in fires])
    np.array([f.frp for f in fires])

    dists = haversine_km(site.lat, site.lon, fire_lats, fire_lons)
    upwind_mask = dists > 0
    if not upwind_mask.any():
        return 0.0

    reach_per_hour = wind.speed_kmh
    if reach_per_hour <= 0:
        return 0.0

    lead_times = dists[upwind_mask] / reach_per_hour
    return float(np.min(lead_times))


def compute_site_forecasts(
    fires: list[Fire], winds: list[Wind], sites: list[Site], grid: list[GridCell]
) -> list[SiteForecast]:
    forecasts = []
    n_hours = len(winds)

    for site in sites:
        site_cell = GridCell(lat=site.lat, lon=site.lon)
        hourly_scores = []
        hourly_tiers = []
        lead_hours = []

        for h in range(n_hours):
            site_res = compute_exposure(fires, winds, [site_cell], hour_idx=h)[0]
            hourly_scores.append(site_res.cell.score)
            hourly_tiers.append(site_res.cell.tier.value)
            lead = estimate_lead_hours(site, fires, winds[h])
            lead_hours.append(lead)

        forecasts.append(
            SiteForecast(
                site_id=site.id,
                site_name=site.name,
                site_type=site.type,
                lat=site.lat,
                lon=site.lon,
                hourly_scores=hourly_scores,
                hourly_tiers=hourly_tiers,
                lead_hours=lead_hours,
            )
        )

    return forecasts


def compute_impact_counters(
    forecasts: list[SiteForecast], grid_results: list
) -> ImpactCounters:
    import numpy as np

    warned_sites = [
        f
        for f in forecasts
        if any(t in ("WARNING", "EMERGENCY") for t in f.hourly_tiers)
    ]
    schools = [f for f in warned_sites if f.site_type == "school"]
    hospitals = [f for f in warned_sites if f.site_type == "hospital"]

    all_lead = []
    for f in warned_sites:
        for i, t in enumerate(f.hourly_tiers):
            if t in ("WARNING", "EMERGENCY") and f.lead_hours[i] > 0:
                all_lead.append(f.lead_hours[i])

    max_score = max((r.cell.score for r in grid_results), default=0)

    return ImpactCounters(
        population_exposed=12_500_000,  # Delhi-NCR approx
        sites_alerted=len(warned_sites),
        schools_alerted=len(schools),
        hospitals_alerted=len(hospitals),
        avg_lead_hours=float(np.mean(all_lead)) if all_lead else 0.0,
        max_score=max_score,
    )


def print_hourly_forecast(forecasts: list[SiteForecast], winds: list[Wind]):
    console.print("\n[bold]48-HOUR FORECAST (every 6h)[/bold]")

    for h in range(0, len(winds), 2):  # Every 6 hours (2 steps = 6h)
        wind = winds[h]
        console.print(
            f"\n  [dim]t={h * 3}h: Wind {wind.dir_deg:.0f}° @ {wind.speed_kmh:.0f} km/h, BLH {wind.blh_m:.0f}m[/dim]"
        )

        forecast_table = Table(show_header=True, header_style="bold")
        forecast_table.add_column("Site")
        forecast_table.add_column("Type")
        forecast_table.add_column("Score")
        forecast_table.add_column("Tier")
        forecast_table.add_column("Lead")

        for f in forecasts:
            score = f.hourly_scores[h]
            tier = f.hourly_tiers[h]
            lead = f.lead_hours[h]
            if tier in ("WARNING", "EMERGENCY"):
                tier_display = (
                    f"[red]{tier}[/red]"
                    if tier == "EMERGENCY"
                    else f"[yellow]{tier}[/yellow]"
                )
                forecast_table.add_row(
                    f.site_name[:20],
                    f.site_type[:8],
                    f"{score:.0f}",
                    tier_display,
                    f"~{lead:.0f}h" if lead > 0 else "N/A",
                )

        if forecast_table.rows:
            console.print(forecast_table)


def generate_html_report(
    fires: list[Fire],
    winds: list[Wind],
    sites: list[Site],
    grid_results: list,
    site_forecasts: list[SiteForecast],
    clusters: list[dict],
    impacts: ImpactCounters,
) -> str:
    from datetime import datetime

    n_hours = len(winds)
    [h * 3 for h in range(n_hours)]

    # Build site forecast rows
    site_rows = ""
    for f in site_forecasts:
        if any(t in ("WARNING", "EMERGENCY") for t in f.hourly_tiers):
            tier_badges = ""
            for h in range(0, n_hours, 2):
                tier = f.hourly_tiers[h]
                color = (
                    "#dc2626"
                    if tier == "EMERGENCY"
                    else "#f59e0b"
                    if tier == "WARNING"
                    else "#10b981"
                    if tier == "WATCH"
                    else "#6b7280"
                )
                score = f.hourly_scores[h]
                tier_badges += f'<span class="badge" style="background:{color}">{tier} ({score:.0f})</span> '

            site_rows += f"""
            <tr>
                <td>{f.site_name}</td>
                <td>{f.site_type}</td>
                <td>{tier_badges}</td>
                <td>{f.lead_hours[0]:.0f}h</td>
            </tr>"""

    # Grid cells top 10
    grid_rows = ""
    for i, r in enumerate(
        sorted(grid_results, key=lambda x: x.cell.score, reverse=True)[:10]
    ):
        color = (
            "#dc2626"
            if r.cell.tier.value == "EMERGENCY"
            else "#f59e0b"
            if r.cell.tier.value == "WARNING"
            else "#10b981"
            if r.cell.tier.value == "WATCH"
            else "#6b7280"
        )
        grid_rows += f"""
        <tr>
            <td>{i + 1}</td>
            <td>{r.cell.lat:.2f}, {r.cell.lon:.2f}</td>
            <td>{r.cell.score:.0f}</td>
            <td><span class="badge" style="background:{color}">{r.cell.tier.value}</span></td>
        </tr>"""

    # Cluster rows
    cluster_rows = ""
    for i, c in enumerate(clusters[:5]):
        cluster_rows += f"""
        <tr>
            <td>{i + 1}</td>
            <td>{c["center_lat"]:.2f}, {c["center_lon"]:.2f}</td>
            <td>{c["count"]}</td>
            <td>{c["total_frp"]:.0f}</td>
            <td>{c["max_frp"]:.0f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stubble Burning Early Warning - Demo Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f8fafc; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); color: white; padding: 30px; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header p {{ margin: 10px 0 0; opacity: 0.9; }}
        .section {{ padding: 20px 30px; border-bottom: 1px solid #e2e8f0; }}
        .section:last-child {{ border-bottom: none; }}
        .section h2 {{ margin: 0 0 15px; color: #1e293b; font-size: 20px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f8fafc; font-weight: 600; color: #475569; }}
        tr:hover {{ background: #f8fafc; }}
        .badge {{ padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; color: white; display: inline-block; margin: 2px; }}
        .impact-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .impact-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; text-align: center; }}
        .impact-value {{ font-size: 32px; font-weight: 700; color: #1e293b; }}
        .impact-label {{ font-size: 14px; color: #64748b; margin-top: 4px; }}
        .forecast-table {{ font-size: 12px; }}
        .forecast-table th, .forecast-table td {{ padding: 6px 8px; }}
        .timestamp {{ color: #94a3b8; font-size: 14px; text-align: right; padding: 0 30px 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Stubble Burning Early Warning</h1>
            <p>Smoke Exposure Forecast for Punjab/Haryana/Delhi-NCR</p>
        </div>
        
        <div class="section">
            <h2>📊 Impact Counters</h2>
            <div class="impact-grid">
                <div class="impact-card">
                    <div class="impact-value">{impacts.population_exposed:,}</div>
                    <div class="impact-label">Population Exposed</div>
                </div>
                <div class="impact-card">
                    <div class="impact-value">{impacts.sites_alerted}</div>
                    <div class="impact-label">Sites Alerted</div>
                </div>
                <div class="impact-card">
                    <div class="impact-value">{impacts.schools_alerted}</div>
                    <div class="impact-label">Schools Alerted</div>
                </div>
                <div class="impact-card">
                    <div class="impact-value">{impacts.hospitals_alerted}</div>
                    <div class="impact-label">Hospitals Alerted</div>
                </div>
                <div class="impact-card">
                    <div class="impact-value">{impacts.avg_lead_hours:.1f}h</div>
                    <div class="impact-label">Avg Lead Time</div>
                </div>
                <div class="impact-card">
                    <div class="impact-value">{impacts.max_score:.0f}</div>
                    <div class="impact-label">Max Exposure Score</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🔥 Fire Clusters (Top 5 by FRP)</h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Location (lat, lon)</th>
                        <th>Fire Count</th>
                        <th>Total FRP (MW)</th>
                        <th>Max FRP (MW)</th>
                    </tr>
                </thead>
                <tbody>
                    {cluster_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>🎯 Top 10 Exposure Grid Cells</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Location</th>
                        <th>Score</th>
                        <th>Tier</th>
                    </tr>
                </thead>
                <tbody>
                    {grid_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>🚨 Site Alerts (48-Hour Forecast)</h2>
            <table class="forecast-table">
                <thead>
                    <tr>
                        <th>Site</th>
                        <th>Type</th>
                        <th>Tier Evolution (every 6h)</th>
                        <th>Lead Time</th>
                    </tr>
                </thead>
                <tbody>
                    {site_rows}
                </tbody>
            </table>
        </div>
        
        <div class="timestamp">
            Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Demo mode: mock data
        </div>
    </div>
</body>
</html>"""
    return html


def main():
    fires, winds, sites, grid = load_mock_data()

    console.print(
        Panel.fit("[bold cyan]STUBBLE BURNING EARLY WARNING - DEMO[/bold cyan]")
    )

    clusters = cluster_fires(fires)
    console.print("\n[bold]FIRE CLUSTERS (top 5 by total FRP)[/bold]")
    cluster_table = Table()
    cluster_table.add_column("#")
    cluster_table.add_column("Location")
    cluster_table.add_column("Fires")
    cluster_table.add_column("Total FRP (MW)")
    cluster_table.add_column("Max FRP (MW)")
    for i, c in enumerate(clusters[:5]):
        cluster_table.add_row(
            str(i + 1),
            f"{c['center_lat']:.2f}, {c['center_lon']:.2f}",
            str(c["count"]),
            f"{c['total_frp']:.0f}",
            f"{c['max_frp']:.0f}",
        )
    console.print(cluster_table)

    wind = winds[0]
    console.print(
        f"\n[bold]WIND (t=0h):[/bold] {wind.dir_deg:.0f}° @ {wind.speed_kmh:.0f} km/h, BLH {wind.blh_m:.0f}m"
    )

    results = compute_exposure(fires, winds, grid, hour_idx=0)

    results_sorted = sorted(results, key=lambda r: r.cell.score, reverse=True)
    console.print("\n[bold]TOP 10 EXPOSURE GRID CELLS[/bold]")
    cell_table = Table()
    cell_table.add_column("#")
    cell_table.add_column("Lat, Lon")
    cell_table.add_column("Score")
    cell_table.add_column("Tier")
    for i, r in enumerate(results_sorted[:10]):
        cell_table.add_row(
            str(i + 1),
            f"{r.cell.lat:.2f}, {r.cell.lon:.2f}",
            f"{r.cell.score:.0f}",
            format_tier(r.cell.tier.value),
        )
    console.print(cell_table)

    site_forecasts = compute_site_forecasts(fires, winds, sites, grid)

    print_hourly_forecast(site_forecasts, winds)

    site_results = []
    for site in sites:
        site_cell = GridCell(lat=site.lat, lon=site.lon)
        site_res = compute_exposure(fires, winds, [site_cell], hour_idx=0)[0]
        lead = estimate_lead_hours(site, fires, wind)
        site_results.append((site, site_res.cell, lead))

    site_results = [
        (s, c, l)
        for s, c, l in site_results
        if c.tier.value in ("WARNING", "EMERGENCY")
    ]
    site_results.sort(key=lambda x: x[1].score, reverse=True)

    console.print("\n[bold]ALERTS (sites with tier >= WARNING)[/bold]")
    if not site_results:
        console.print("[yellow]No sites above WARNING threshold[/yellow]")
    else:
        alert_table = Table()
        alert_table.add_column("Tier")
        alert_table.add_column("Site")
        alert_table.add_column("Type")
        alert_table.add_column("Action")
        alert_table.add_column("Lead Time")
        for site, cell, lead in site_results:
            if cell.tier.value == "EMERGENCY":
                action = "Stay indoors, wear N95 outdoors"
            else:
                action = "Move sports indoors tomorrow"
            alert_table.add_row(
                format_tier(cell.tier.value),
                site.name,
                site.type,
                action,
                f"~{lead:.0f}h",
            )
        console.print(alert_table)

    impacts = compute_impact_counters(site_forecasts, results)
    console.print("\n[bold]IMPACT COUNTERS[/bold]")
    impact_table = Table()
    impact_table.add_column("Metric")
    impact_table.add_column("Value")
    impact_table.add_row("Population Exposed", f"{impacts.population_exposed:,}")
    impact_table.add_row("Sites Alerted", str(impacts.sites_alerted))
    impact_table.add_row("Schools Alerted", str(impacts.schools_alerted))
    impact_table.add_row("Hospitals Alerted", str(impacts.hospitals_alerted))
    impact_table.add_row("Avg Lead Time", f"{impacts.avg_lead_hours:.1f}h")
    impact_table.add_row("Max Exposure Score", f"{impacts.max_score:.0f}")
    console.print(impact_table)

    html = generate_html_report(
        fires, winds, sites, results, site_forecasts, clusters, impacts
    )
    output_path = Path(__file__).parent.parent / "demo_report.html"
    output_path.write_text(html, encoding="utf-8")
    console.print(f"\n[bold green]HTML report saved to:[/bold green] {output_path}")

    console.print("\n[bold green]Demo complete[/bold green]")


if __name__ == "__main__":
    main()
