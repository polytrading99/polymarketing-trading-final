import asyncio
from decimal import Decimal

from poly_data.polymarket_client import PolymarketClient
from app.config import ConfigRepository


async def main() -> None:
    """
    Simple one-off script to place a small BUY order on the first active market.

    Requirements:
      - DATABASE_URL points to the same DB used by the backend
      - PK and BROWSER_ADDRESS are set in the environment (or .env)
      - At least one market has an active, running bot (status=active and BotRun.status='running')
    """
    repo = ConfigRepository()
    markets = await repo.list_markets(active_only=True)

    if not markets:
        print("No active markets with running bots found in database.")
        print("Make sure you have started a bot for at least one market.")
        return

    market = markets[0]
    print(f"Using market:\n  question={market.question}\n  condition_id={market.condition_id}")

    token_id = market.token_yes
    neg_risk = market.neg_risk

    print(f"Token YES id: {token_id}")
    print(f"Neg risk: {neg_risk}")

    client = PolymarketClient()

    # Very small test order
    price = 0.5
    size = 1.0

    print(f"Placing test BUY order: token={token_id}, price={price}, size={size}")
    try:
        resp = client.create_order(
            marketId=str(token_id),
            action="BUY",
            price=price,
            size=size,
            neg_risk=bool(neg_risk),
        )
        print("Order response:", resp)
    except Exception as e:
        print("Failed to place test order:", e)


if __name__ == "__main__":
    asyncio.run(main())


