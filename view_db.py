"""Utility script to fetch and print all stored companies from the PostgreSQL database."""
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.database import get_connection_params
import asyncpg


async def main():
    print("Connecting to PostgreSQL database...")
    try:
        params = await get_connection_params()
        conn = await asyncpg.connect(**params)
        try:
            print(f"Connected. Fetching rows from table 'companies'...")
            rows = await conn.fetch("SELECT id, query, name, category, website, phone, email FROM companies ORDER BY id DESC")
            
            if not rows:
                print("\nNo records found in 'companies' table.")
                return

            print(f"\nFound {len(rows)} record(s) in database:\n")
            print(f"{'ID':<5} | {'Query':<25} | {'Name':<30} | {'Category':<20} | {'Email':<25}")
            print("-" * 115)
            for r in rows:
                # Truncate strings for clean formatting
                q = (r['query'] or '')[:23] + '..' if len(r['query'] or '') > 23 else (r['query'] or '')
                n = (r['name'] or '')[:28] + '..' if len(r['name'] or '') > 28 else (r['name'] or '')
                cat = (r['category'] or '')[:18] + '..' if len(r['category'] or '') > 18 else (r['category'] or '')
                email = r['email'] or '—'
                
                print(f"{r['id']:<5} | {q:<25} | {n:<30} | {cat:<20} | {email:<25}")
                
        finally:
            await conn.close()
    except Exception as e:
        print(f"\nError connecting or reading database: {e}")


if __name__ == "__main__":
    asyncio.run(main())
