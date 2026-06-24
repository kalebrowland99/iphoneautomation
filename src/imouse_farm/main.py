"""Application entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from imouse_farm.app import create_application
from imouse_farm.dashboard.app import create_app
from imouse_farm.utils.env_file import load_env_file
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


async def run_server(config_path: str) -> None:
    """Start the iMouse Farm application with dashboard."""
    app_instance = await create_application(config_path)
    await app_instance.start()

    fastapi_app = create_app(app_instance.config, app_instance)
    config = uvicorn.Config(
        fastapi_app,
        host=app_instance.config.dashboard.host,
        port=app_instance.config.dashboard.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await app_instance.stop()


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="iMouse Farm - Multi-device iPhone automation")
    parser.add_argument(
        "-c", "--config",
        default="config/config.yaml",
        help="Path to configuration file",
    )
    args = parser.parse_args()
    load_env_file()

    try:
        asyncio.run(run_server(args.config))
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        sys.exit(0)


if __name__ == "__main__":
    cli()
