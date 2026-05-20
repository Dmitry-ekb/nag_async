import asyncpg

DATABASE_URL = "postgresql://ekbicp:1234@localhost:5432/nagdb"

async def connect_db():
    conn = await asyncpg.connect(DATABASE_URL)
    return conn

async def create_table(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog (
            sku TEXT PRIMARY KEY,
            guid TEXT NOT NULL,
            title TEXT NOT NULL
        )
        """)
async def save_catalog(conn, catalog_dict):
    for sku, info in catalog_dict.items():
        await conn.execute("""
            INSERT INTO catalog (sku, guid, title) VALUES
            ($1, $2, $3) ON CONFLICT (sku) DO UPDATE SET guid = $2, title = $3""",
            sku, info["guid"], info["title"])
        
async def load_catalog(conn):
    rows = await conn.fetch("SELECT sku, guid, title FROM catalog")
    catalog = {}
    for row in rows:
        catalog[row["sku"]] = {"guid": row["guid"], "sku": row["sku"], "title": row["title"]}
    return catalog
    