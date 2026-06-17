"""Enable `python -m tools.backtest_v2`."""

import sys

from tools.backtest_v2.cli import main

if __name__ == "__main__":
    sys.exit(main())
