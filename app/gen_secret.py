from __future__ import annotations

import argparse
import secrets


def generate(nbytes: int = 48) -> str:
    return secrets.token_urlsafe(nbytes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SECRET_KEY for .env")
    parser.add_argument(
        "-n",
        "--bytes",
        type=int,
        default=48,
        help="entropy in bytes (default 48 → ~64 char urlsafe string)",
    )
    args = parser.parse_args()
    if args.bytes < 32:
        raise SystemExit("use at least 32 bytes of entropy")
    print(generate(args.bytes))


if __name__ == "__main__":
    main()
