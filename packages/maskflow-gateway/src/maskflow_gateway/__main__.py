"""``python -m maskflow_gateway`` / ``maskflow-gateway`` -- run the ASGI
app under uvicorn. All configuration is via ``MASKFLOW_GATEWAY_*`` env
vars (see ``maskflow_gateway.config.Settings``); only host/port/workers are
CLI flags.
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="maskflow-gateway")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - a proxy binds all interfaces
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    uvicorn.run(
        "maskflow_gateway.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
        access_log=False,
    )


if __name__ == "__main__":
    main()
