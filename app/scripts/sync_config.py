import asyncio
from typing import Optional

from loguru import logger

from app.config import GoogleSheetConfigProvider
from app.config.repository import ConfigRepository


async def sync(
    source_provider: Optional[GoogleSheetConfigProvider] = None,
    repository: Optional[ConfigRepository] = None,
) -> None:
    repository = repository or ConfigRepository()
    provider = source_provider or GoogleSheetConfigProvider()

    logger.info("Fetching configuration from Google Sheets...")
    snapshot = await provider.fetch()
    logger.info(
        "Fetched {markets} markets and {strategies} strategies",
        markets=len(snapshot.markets),
        strategies=len(snapshot.strategies),
    )

    logger.info("Applying snapshot to database...")
    await repository.apply_snapshot(snapshot)
    logger.success("Configuration synchronized successfully.")


def main() -> None:
    asyncio.run(sync())


if __name__ == "__main__":
    main()

