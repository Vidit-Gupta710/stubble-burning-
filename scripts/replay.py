"""
Replay script: runs full pipeline on saved snapshot, produces all demo outputs.
Usage: python -m scripts.replay
"""

import shutil
from pathlib import Path

from scripts.backtest import main as run_backtest
from scripts.generate_mock import main as gen_mock
from scripts.run_demo import main as run_demo


def main():
    print("=" * 60)
    print("STUBBLE BURNING EARLY WARNING - FULL REPLAY")
    print("=" * 60)

    # 1. Generate mock data
    print("\n[1/4] Generating mock data...")
    gen_mock()

    # 2. Run demo (produces HTML report)
    print("\n[2/4] Running demo pipeline...")
    run_demo()

    # 3. Run backtest
    print("\n[3/4] Running backtest validation...")
    run_backtest()

    # 4. Copy frontend data
    print("\n[4/4] Preparing frontend...")
    data_src = Path(__file__).parent.parent / "data"
    frontend_data = Path(__file__).parent.parent / "frontend" / "data"
    frontend_data.mkdir(parents=True, exist_ok=True)

    for fname in [
        "mock_fires.json",
        "mock_wind.json",
        "mock_sites.json",
        "mock_grid.json",
    ]:
        shutil.copy2(data_src / fname, frontend_data / fname)

    print("\n" + "=" * 60)
    print("REPLAY COMPLETE")
    print("=" * 60)
    print("\nOutputs generated:")
    print("  [REPORT] demo_report.html     - Full HTML report")
    print("  [BACKTEST] backtest_results.json - Backtest correlations")
    print("  [DASHBOARD] frontend/index.html   - Interactive dashboard")
    print("  [DATA] frontend/data/        - Data for dashboard")
    print("\nTo view dashboard: open frontend/index.html in browser")
    print("To run demo again: python -m scripts.run_demo")


if __name__ == "__main__":
    main()
