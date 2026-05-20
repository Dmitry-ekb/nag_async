from datetime import datetime
import asyncio
import aiohttp
from fastapi import FastAPI
from db import connect_db, create_table, load_catalog, save_catalog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.on_event("startup")
async def startup():
    print("🚀 Запуск сервера...")
    conn_db = await connect_db()
    print("✅ Подключение к БД")
    await create_table(conn_db)
    print("✅ Таблица готова")
    catalog = await load_catalog(conn_db)
    print(f"📦 Каталог из БД: {len(catalog)} записей")
    app.state.conn_db = conn_db
            
@app.get("/search")
async def search(articles: str = "", api_key: str = "", request: Request = None):
    conn_db = request.app.state.conn_db
    article_list = [a.strip().lower() for a in articles.split(",") if a.strip()]
    
    if not article_list:
        return {"error": "Не указаны артикулы"}
    
    catalog = await load_catalog(conn_db)
    
    async with aiohttp.ClientSession() as session:
        prices, stocks, names = await asyncio.gather(
            load_prices(session, api_key),
            load_stocks(session, api_key),
            load_stock_names(session, api_key),
        )
    
    results = []
    for article in article_list:
        if article not in catalog:
            results.append({"article": article, "found": False})
            continue
        
        info = catalog[article]
        guid = info["guid"]
        
        result_item = {
            "article": article,
            "title": info["title"],
            "found": True,
        }
        
        if guid in prices:
            p = prices[guid]
            result_item["prices"] = {
                "retail": p.get("priceRetail"),
                "wholesale": p.get("priceWholesale"),
                "wholesalelarge": p.get("priceWholesalelarge"),
                "dealer": p.get("priceDealer"),
            }
        else:
            result_item["prices"] = None
        
        if guid in stocks:
            total_free = 0
            total_full = 0
            stock_list = []
            for s in stocks[guid]:
                if s["free"] or s["full"]:
                    stock_list.append({
                        "name": names.get(s["stockGuid"], s["stockGuid"]),
                        "free": s["free"],
                        "full": s["full"],
                        "date": format_date(s["date"]) if s.get("date") else None,
                    })
                    total_free += s["free"]
                    total_full += s["full"]
            result_item["stocks"] = stock_list
            result_item["total_free"] = total_free
            result_item["total_full"] = total_full
        else:
            result_item["stocks"] = []
            result_item["total_free"] = 0
            result_item["total_full"] = 0
        
        results.append(result_item)
    
    return results
    
@app.get("/update-catalog")
async def update_catalog(api_key: str = "", request: Request = None):
    conn_db = request.app.state.conn_db
    async with aiohttp.ClientSession() as session:
        catalog_dict = await fetch_catalog_from_api(session, api_key)
        await save_catalog(conn_db, catalog_dict)
    return {"ok": True, "count": len(catalog_dict)}

@app.get("/catalog-status")
async def catalog_status(request: Request):
    conn_db = request.app.state.conn_db
    catalog = await load_catalog(conn_db)
    return {"loaded": len(catalog) > 0, "count": len(catalog)}
   
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

def get_timestamp():
    return datetime.now().strftime("%Y%m%d")


def format_date(date_str):
    if not date_str:
        return ""
    parts = date_str.split("-")
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


async def fetch_json(session, endpoint, api_key):
    response = await session.get(f'https://b2b.nag.ru/api/export/{endpoint}?hash={api_key}&tm={get_timestamp()}')
    return await response.json()


async def fetch_catalog_from_api(session, api_key):
    data = await fetch_json(session, "products", api_key)
    catalog = {}
    for item in data:
        if item.get("sku") and item.get("guid"):
            clean_sku = item["sku"].replace("\\", "").replace("/", "").lower()
            catalog[clean_sku] = {
                "guid": item["guid"],
                "sku": item["sku"],
                "title": item.get("title", "")
            }
    return catalog


async def load_prices(session, api_key):
    data = await fetch_json(session, "product_prices", api_key)
    prices = {}
    for item in data:
        if item.get("itemGuid"):
            guid = item["itemGuid"]
            prices[guid] = {
                "priceRetail": item.get("priceRetail"),
                "priceWholesale": item.get("priceWholesale"),
                "priceWholesalelarge": item.get("priceWholesalelarge"),
                "priceDealer": item.get("priceDealer"),
            }
    return prices


async def load_stocks(session, api_key):
    data = await fetch_json(session, "product_stocks", api_key)
    stocks = {}
    for item in data:
        if item.get("itemGuid"):
            guid = item["itemGuid"]
            if guid not in stocks:
                stocks[guid] = []
            stocks[guid].append({
                "stockGuid": item.get("stockGuid"),
                "free": item.get("free"),
                "full": item.get("full"),
                "unit": item.get("unit"),
                "date": item.get("date"),
                "type": item.get("type"),
            })
    return stocks


async def load_stock_names(session, api_key):
    data = await fetch_json(session, "stocks", api_key)
    result = {}
    for item in data:
        result[item["guid"]] = item["name"]
    return result


# async def main():
#     print("Вставьте API ключ:")
#     api_key = input("API-ключ: ").strip()
#     print("Вставьте артикулы (пустая строка — завершить):")
#     articles = []
#     while True:
#         line = input().strip()
#         if not line:
#             break
#         articles.append(line.lower())

#     try:
#         async with aiohttp.ClientSession() as session:
#             catalog, prices, stocks, names = await asyncio.gather(
#                 load_catalog(session, api_key),
#                 load_prices(session, api_key),
#                 load_stocks(session, api_key),
#                 load_stock_names(session, api_key),
#             )
#     except Exception as e:
#         print(f"❌ Ошибка при загрузке данных: {e}")
#         return

#     for article in articles:
#         if article not in catalog:
#             print(f'Артикула: {article} нет в каталоге')
#         else:
#             info = catalog[article]
#             guid = info["guid"]
#             print(f'Артикул: {info["sku"]} — {info["title"]}')
#             if guid not in prices:
#                 print(f'По данному артикулу {article} нет цен')
#             else:
#                 p = prices[guid]
#                 print("Цены:")
#                 if p["priceRetail"]:
#                     print(f'Розница: {p["priceRetail"]}')
#                 if p["priceWholesale"]:
#                     print(f'Опт: {p["priceWholesale"]}')
#                 if p["priceWholesalelarge"]:
#                     print(f'Спец: {p["priceWholesalelarge"]}')
#                 if p["priceDealer"]:
#                     print(f'Дилер: {p["priceDealer"]}')
#             if guid not in stocks:
#                 print(f'Данного артикула в наличии нет')
#             else:
#                 total_free = 0
#                 total_full = 0
#                 for s in stocks[guid]:
#                     if s["free"] or s["full"]:
#                         stock_name = names.get(s["stockGuid"], s["stockGuid"])
#                         print(f"{stock_name}: свободно {s['free']} шт, всего {s['full']} шт")
#                         if s.get("date"):
#                             print(f"(поступление: {format_date(s['date'])})")
#                         total_free += s["free"]
#                         total_full += s["full"]
#                 print(f"Итого: свободно {total_free} шт, всего {total_full} шт")
#             print()


if __name__ == "__main__":
    asyncio.run(main())