"""PyInstaller entrypoint for Wealthsimple Prospector.

Default behavior starts the web app server.
CLI behavior is available via:
    wealthsimple-prospector cli <subcommands...>
"""

from __future__ import annotations

import sys

from linkedin_leads.app import main as app_main
from linkedin_leads.debug import main as cli_main


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        cli_main()
    else:
        app_main()
