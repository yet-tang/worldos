from __future__ import annotations

import argparse

from .web_console_extensions import serve_world_console


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-inspector")
    parser.add_argument("--db", required=True, help="Legacy/default SQLite world database; its parent directory also stores created worlds")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"WorldOS Console: http://{args.host}:{args.port}")
    serve_world_console(args.db, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
