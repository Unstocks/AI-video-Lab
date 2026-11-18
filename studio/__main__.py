"""CLI entrypoint for AI Video Lab Studio (`python -m studio`)."""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m studio",
        description="Launch AI Video Lab Unified Top-Supervisor Studio (loopback only).",
    )
    parser.add_argument("--port", type=int, default=4760, help="Loopback TCP port (default: 4760)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the browser tab on startup.",
    )
    args = parser.parse_args(argv)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"AI Video Lab Studio -> {url} (loopback only)")

    if not args.no_browser:
        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "studio.server:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
