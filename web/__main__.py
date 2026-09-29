"""`python -m web` — start the studio on this machine and open it in the browser.

Local only (127.0.0.1): the studio is a desktop tool, not a shared server.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m web", description="PLANFGEN — studio web")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    import uvicorn

    from web.server import create_app

    url = f"http://{args.host}:{args.port}/"
    print(f"PLANFGEN studio : {url}  (Ctrl+C pour arrêter)")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":  # the guard a Windows process pool (spawn) needs
    main()
