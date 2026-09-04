import asyncpg
import logging
import os
from contextlib import asynccontextmanager

logger = logging.getLogger("scalping-arise-db")

class TimescaleDB:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=2, max_size=10)
        logger.info("Connected to TimescaleDB.")
        await self.setup_schema()

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from TimescaleDB.")

    async def setup_schema(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticks (
                    time        TIMESTAMPTZ       NOT NULL,
                    symbol      TEXT              NOT NULL,
                    price       DOUBLE PRECISION  NOT NULL,
                    volume      DOUBLE PRECISION  NOT NULL,
                    provider    TEXT              NOT NULL
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE);
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    time        TIMESTAMPTZ       NOT NULL,
                    symbol      TEXT              NOT NULL,
                    feature_name TEXT             NOT NULL,
                    value       DOUBLE PRECISION  NOT NULL
                );
            """)
            await conn.execute("""
                SELECT create_hypertable('features', 'time', if_not_exists => TRUE);
            """)
            logger.info("TimescaleDB schema configured.")

    async def insert_tick(self, timestamp: int, symbol: str, price: float, volume: float, provider: str):
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ticks (time, symbol, price, volume, provider)
                    VALUES (to_timestamp($1), $2, $3, $4, $5)
                """, timestamp, symbol, price, volume, provider)
        except Exception as e:
            logger.warning(f"Failed to insert tick: {e}")

    async def insert_feature(self, timestamp: int, symbol: str, feature_name: str, value: float):
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO features (time, symbol, feature_name, value)
                    VALUES (to_timestamp($1), $2, $3, $4)
                """, timestamp, symbol, feature_name, value)
        except Exception as e:
            logger.warning(f"Failed to insert feature: {e}")

# DSN from environment, fallback to localhost for local dev
_dsn = os.environ.get("TIMESCALE_DSN", "postgres://postgres:postgres@localhost:5432/market_data")
db = TimescaleDB(dsn=_dsn)
