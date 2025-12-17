from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.db.sqlserver import get_products, get_sales_12m, count_products
from app.services.product_formatter import format_products
import math


app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
def root():
    return {"status":"ok"}

@app.get("/zproveart", response_class=HTMLResponse)
def zproveart_home(request: Request, page: str = "1"):
    try:
        page = int(page)
    except:
        page = 1
    PAGE_SIZE = 6
    total = count_products()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    products = get_products(page, PAGE_SIZE)

    itmrefs = [p["ITMREF_0"] for p in products if p.get("ITMREF_0")]
    sales_rows = get_sales_12m(itmrefs)

    products = format_products(products, sales_rows=sales_rows)


    return templates.TemplateResponse(
        "product.html",
        {
            "request": request,
            "products": products,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_pages": total_pages,
        },
    ) 