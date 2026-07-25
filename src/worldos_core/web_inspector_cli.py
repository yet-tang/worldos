from __future__ import annotations

import argparse

from .web_inspector import serve_web_inspector


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-inspector")
    parser.add_argument("--db", required=True, help="SQLite world database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"WorldOS Inspector: http://{args.host}:{args.port}")
    serve_web_inspector(args.db, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
