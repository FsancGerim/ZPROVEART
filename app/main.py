from fastapi import FastAPI, Request, Query, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.db.sqlserver import (
    get_products,
    get_sales_12m,
    count_products,
    get_fams_cached,
    get_subfams_cached,
    get_eta_rows,
)
from app.services.product_formatter import format_products
from app.services.filters import parse_date
from app.services.excel_exporter import ExcelExporter, append_row_daily
from app.config import EXPORT_DIR
from app.routes import fotos
import math

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(fotos.router)

exporter = ExcelExporter(EXPORT_DIR)


@app.get("/")
def root():
    return {"status": "ok"}


# Endpoint para cargar subfamilias al vuelo (AJAX) - 1 familia
@app.get("/api/zproveart/subfamilies")
def api_subfamilies(family: str):
    family = (family or "").strip()
    return {"family": family, "subfamilies": get_subfams_cached(family)}


@app.get("/zproveart", response_class=HTMLResponse)
def zproveart_home(
    request: Request,
    page: str = "1",
    family: list[str] = Query(default=[]),
):
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

    # Subfamilias por familia (vienen como subfam_02=0201&subfam_02=0203...)
    subfams_by_fam: dict[str, list[str]] = {}
    for fam in family_list:
        key = f"subfam_{fam}"
        vals = request.query_params.getlist(key)
        vals = [str(v).strip() for v in vals if v and str(v).strip()]
        if vals:
            subfams_by_fam[fam] = vals

    # Para el pager: repetir params subfam_XX actuales tal cual
    subfam_params: list[tuple[str, str]] = []
    for fam, subs in subfams_by_fam.items():
        key = f"subfam_{fam}"
        for v in subs:
            subfam_params.append((key, v))

    PAGE_SIZE = 3

    total = count_products(
        families=family_list,
        subfams_by_fam=subfams_by_fam,
        date_from=date_from,
        date_to=date_to,
        supp_from=supp_from,
        supp_to=supp_to,
        comp_from=comp_from,
        comp_to=comp_to,
        art_from=art_from,
        art_to=art_to,
    )

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))

    products = get_products(
        page=page,
        page_size=PAGE_SIZE,
        families=family_list,
        subfams_by_fam=subfams_by_fam,
        date_from=date_from,
        date_to=date_to,
        supp_from=supp_from,
        supp_to=supp_to,
        comp_from=comp_from,
        comp_to=comp_to,
        art_from=art_from,
        art_to=art_to,
    )

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
            # Para mantener estado / debug
            "subfams_by_fam": subfams_by_fam,
            # Para el pager (muy importante)
            "subfam_params": subfam_params,
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
