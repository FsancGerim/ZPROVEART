from fastapi import FastAPI, Request, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.db.sqlserver import get_products, get_sales_12m, count_products, get_fams_cached, get_eta_rows
from app.services.product_formatter import format_products
from app.services.filters import parse_date
from app.services.excel_exporter import ExcelExporter, append_row_daily
from app.config import EXPORT_DIR
from app.routes import fotos
from playwright.sync_api import sync_playwright
from urllib.parse import quote
from pathlib import Path
import math


app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(fotos.router)

exporter = ExcelExporter(EXPORT_DIR)


@app.get("/")
def root():
    return {"status":"ok"}

@app.get("/zproveart", response_class=HTMLResponse)
def zproveart_home(request: Request, page: str = "1", family: list[str] = Query(default=[])):
    try:
        page = int(page)
    except:
        page = 1

    # fechas (sanitize)
    date_from = parse_date(request.query_params.get("from"))
    date_to = parse_date(request.query_params.get("to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    # proveedor
    supp_from = request.query_params.get("supp_from")
    supp_to = request.query_params.get("supp_to")
    # comprador
    comp_from = request.query_params.get("comp_from")
    comp_to = request.query_params.get("comp_to")
    # artículos
    art_from = request.query_params.get("art_from")
    art_to = request.query_params.get("art_to")

    family_list = [str(f).strip() for f in family if f and str(f).strip()]
    PAGE_SIZE = 3
    total = count_products(family_list, date_from, date_to, supp_from, supp_to, comp_from, comp_to, art_from, art_to)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    products = get_products(page, PAGE_SIZE, family_list, date_from, date_to, supp_from, supp_to, comp_from, comp_to, art_from, art_to)

    itmrefs = [p["ITMREF_0"] for p in products if p.get("ITMREF_0")]
    sales_rows = get_sales_12m(itmrefs)
    eta_rows = get_eta_rows(itmrefs)

    products = format_products(products, sales_rows=sales_rows, eta_rows=eta_rows)
    families = get_fams_cached()


    return templates.TemplateResponse(
        "pages/zproveart.html",
        {
            "request": request,
            "products": products,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_pages": total_pages,
            "families": families,
            "family_list": family_list,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
            "supp_from": supp_from,
            "supp_to": supp_to,
            "comp_from": comp_from,
            "comp_to": comp_to,
            "art_from": art_from,
            "art_to": art_to,
        },
    ) 

@app.post("/zproveart/submit")
async def zproveart_submit(request: Request):
    form = await request.form()

    itmref = (form.get("itmref") or "").strip()
    comment = (form.get("comment") or "").strip()

    # Checkbox HTML: si no viene, es False; si viene, puede ser "1" o "on"
    selected_raw = form.get("selected")
    selected = selected_raw in ("1", "on", "true", "True")

    if itmref:
        append_row_daily(
            exporter,
            itmref=itmref,
            selected=selected,
            comment=comment,
        )

    return Response(status_code=204)


@app.get("/zproveart/pdf")
def zproveart_pdf(request: Request, page: str = "1", family: list[str] = Query(default=[])):
    # page sanitize
    try:
        page = int(page)
    except:
        page = 1

    # fechas (sanitize)
    date_from = parse_date(request.query_params.get("from"))
    date_to = parse_date(request.query_params.get("to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    # proveedor
    supp_from = request.query_params.get("supp_from")
    supp_to = request.query_params.get("supp_to")
    # comprador
    comp_from = request.query_params.get("comp_from")
    comp_to = request.query_params.get("comp_to")
    # artículos
    art_from = request.query_params.get("art_from")
    art_to = request.query_params.get("art_to")

    family_list = [str(f).strip() for f in family if f and str(f).strip()]

    # 👇 tamaño para PDF (tarjetas más compactas, más por página)
    PRINT_PAGE_SIZE = 18

    total = count_products(
        family_list, date_from, date_to,
        supp_from, supp_to,
        comp_from, comp_to,
        art_from, art_to
    )
    total_pages = max(1, math.ceil(total / PRINT_PAGE_SIZE))
    page = max(1, min(page, total_pages))

    products = get_products(
        page, PRINT_PAGE_SIZE,
        family_list, date_from, date_to,
        supp_from, supp_to,
        comp_from, comp_to,
        art_from, art_to
    )

    itmrefs = [p["ITMREF_0"] for p in products if p.get("ITMREF_0")]
    sales_rows = get_sales_12m(itmrefs) if itmrefs else []
    eta_rows = get_eta_rows(itmrefs) if itmrefs else []

    products = format_products(products, sales_rows=sales_rows, eta_rows=eta_rows)

    # ✅ NUEVO: leer CSS y pasarlo al template (INLINE CSS)
    base_dir = Path(__file__).resolve().parent  # .../app
    cards_css_path = base_dir / "static" / "css" / "zproveart" / "_cards.css"
    pdf_css_path   = base_dir / "static" / "css" / "zproveart" / "pdf.css"

    cards_css = cards_css_path.read_text(encoding="utf-8") if cards_css_path.exists() else ""
    pdf_css = pdf_css_path.read_text(encoding="utf-8") if pdf_css_path.exists() else ""

    # Render Jinja -> HTML string (importante pasar request)
    html = templates.get_template("pages/zproveart_pdf.html").render({
        "request": request,
        "products": products,
        "page": page,
        "page_size": PRINT_PAGE_SIZE,
        "total_pages": total_pages,
        "family_list": family_list,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "supp_from": supp_from,
        "supp_to": supp_to,
        "comp_from": comp_from,
        "comp_to": comp_to,
        "art_from": art_from,
        "art_to": art_to,

        # ✅ NUEVO: variables que tu template usa en <style>{{ ... }}</style>
        "cards_css": cards_css,
        "pdf_css": pdf_css,
    })

    # Cargar HTML como "navegación real" (data URL)
    data_url = "data:text/html;charset=utf-8," + quote(html)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[
                "--disable-dev-shm-usage",
                # en Windows no hace falta, pero no molesta; en Linux/Docker sí
                "--no-sandbox",
            ]
        )
        pw_page = browser.new_page()
        pw_page.goto(data_url, wait_until="networkidle")

        pdf_bytes = pw_page.pdf(
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
        )

        browser.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="zproveart.pdf"'},
    )