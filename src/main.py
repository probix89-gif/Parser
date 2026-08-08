"""Entry point — starts the Yahoo Mass Dork Parser Bot."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from src.bot.handlers import DorkBot
from src.models.config import load_config


def main() -> None:
    """Initialize and start the bot."""
    logger.info("Starting Yahoo Mass Dork Parser Bot...")
    config = load_config()

    if not config.token:
        logger.error(
            "TELEGRAM_BOT_TOKEN not set! "
            "Set it in .env or as environment variable."
        )
        sys.exit(1)

    logger.info(
        f"Config: max_concurrency={config.max_concurrency}, "
        f"max_dork_concurrency={config.max_dork_concurrency}, "
        f"max_pages={config.max_pages}, "
        f"rate_limit={config.rate_limit_per_sec}"
    )

    bot = DorkBot(config)
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
