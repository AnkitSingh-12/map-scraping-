"""PostgreSQL Database Layer using asyncpg.

Handles automatic database/table creation and upserting company records.
Resilient against connection errors to prevent breaking the core scraper if the DB is offline.
"""
import asyncio
import logging
import asyncpg
from typing import List
from .config import settings
from .models import Company

logger = logging.getLogger("app.database")


async def get_connection_params(db_name: str | None = None) -> dict:
    """Return connection parameters for asyncpg."""
    return {
        "user": settings.pg_user,
        "password": settings.pg_password,
        "host": settings.pg_host,
        "port": settings.pg_port,
        "database": db_name or settings.pg_database,
    }


async def init_db():
    """Attempt to initialize the PostgreSQL database and tables.

    If the database 'map_scrap' does not exist, it will connect to the default
    'postgres' database, create 'map_scrap', and then initialize the schema.
    """
    logger.info("Initializing database...")
    try:
        # 1. Check if the target database exists by connecting to 'postgres'
        conn = None
        try:
            params = await get_connection_params(db_name="postgres")
            conn = await asyncpg.connect(**params)
            
            # Check if target database exists
            dbs = await conn.fetch("SELECT datname FROM pg_database WHERE datname = $1", settings.pg_database)
            if not dbs:
                logger.info(f"Database '{settings.pg_database}' not found. Creating it...")
                # Cannot run CREATE DATABASE in a transaction, asyncpg requires it outside
                await conn.execute(f'CREATE DATABASE "{settings.pg_database}"')
                logger.info(f"Database '{settings.pg_database}' created successfully.")
        except Exception as e:
            logger.warning(f"Could not check/create database using 'postgres' connection: {e}")
        finally:
            if conn:
                await conn.close()

        # 2. Connect to the target database and create the companies table
        target_params = await get_connection_params()
        conn = await asyncpg.connect(**target_params)
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    query TEXT,
                    name TEXT NOT NULL,
                    maps_url TEXT UNIQUE,
                    website TEXT,
                    phone TEXT,
                    email TEXT,
                    address TEXT,
                    category TEXT,
                    rating TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Create index on query and maps_url for fast lookups
                CREATE INDEX IF NOT EXISTS idx_companies_query ON companies(query);
            """)
            logger.info("Database schema initialized successfully.")
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Database initialization failed: {e}. Scraper will run in memory-only mode.")


async def save_companies(query: str, companies: List[Company], log=lambda m: None) -> bool:
    """Upsert a list of companies into the PostgreSQL database."""
    if not companies:
        return False

    log("Saving results to PostgreSQL database...")
    try:
        target_params = await get_connection_params()
        conn = await asyncpg.connect(**target_params)
        try:
            # Prepare upsert statement
            query_str = """
                INSERT INTO companies (query, name, maps_url, website, phone, email, address, category, rating)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (maps_url) DO UPDATE SET
                    query = EXCLUDED.query,
                    name = EXCLUDED.name,
                    website = EXCLUDED.website,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    address = EXCLUDED.address,
                    category = EXCLUDED.category,
                    rating = EXCLUDED.rating;
            """
            
            # Execute batch inserts
            records = [
                (
                    query,
                    c.name,
                    c.maps_url,
                    c.website,
                    c.phone,
                    c.email,
                    c.address,
                    c.category,
                    c.rating
                )
                for c in companies
            ]
            
            await conn.executemany(query_str, records)
            log(f"Successfully saved {len(companies)} companies to PostgreSQL.")
            return True
        finally:
            await conn.close()
    except Exception as e:
        error_msg = f"Failed to save to PostgreSQL: {e}"
        logger.error(error_msg)
        log(f"⚠ Warning: {error_msg} (Results are still returned to UI)")
        return False
