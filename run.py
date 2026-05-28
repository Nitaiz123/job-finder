"""
Daily run: (optionally) discover new companies, fetch fresh jobs, rebuild dashboard.
"""

from config import DISCOVERY_ON_EACH_RUN
from fetch import main as fetch_main
from dashboard import build_dashboard


if __name__ == "__main__":
    if DISCOVERY_ON_EACH_RUN:
        try:
            from discover import run_discovery
            run_discovery()
            print()
        except Exception as e:
            print(f"(Discovery step skipped: {e})\n")

    fetch_main()
    print()
    build_dashboard()
    print("\nDone. Open dashboard.html in your browser.")
