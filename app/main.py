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
    get_products_all
)
from app.services.product_formatter import format_products
from app.services.filters import parse_date
from app.services.excel_exporter import ExcelExporter, append_row_daily
from app.config import EXPORT_DIR
from app.routes import fotos
from playwright.sync_api import sync_playwright
from pathlib import Path
import math

from datetime import date
from io import BytesIO

PdfMerger = None
PdfWriter = None
_pypdf_import_error = None

try:
    # pypdf moderno (ojo: PdfMerger ya no existe en 6.x, esto fallará y cae al fallback)
    from pypdf import PdfMerger  # type: ignore
except Exception as e:
    _pypdf_import_error = e
    try:
        # fallback: PdfWriter existe
        from pypdf import PdfWriter  # type: ignore
    except Exception as e2:
        _pypdf_import_error = e2

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(fotos.router)

exporter = ExcelExporter(EXPORT_DIR)


def _default_years() -> list[int]:
    y = date.today().year
    return [y, y - 1]


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

    # ✅ años para ZTCOMVEN: año actual + anterior
    years = _default_years()

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
        years=years,  # ✅ antes year=2025
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


@app.get("/zproveart/pdf")
def zproveart_pdf(request: Request, family: list[str] = Query(default=[])):
    # filtros
    date_from = parse_date(request.query_params.get("from"))
    date_to = parse_date(request.query_params.get("to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    supp_from = request.query_params.get("supp_from")
    supp_to = request.query_params.get("supp_to")
    comp_from = request.query_params.get("comp_from")
    comp_to = request.query_params.get("comp_to")
    art_from = request.query_params.get("art_from")
    art_to = request.query_params.get("art_to")

    family_list = [str(f).strip() for f in family if f and str(f).strip()]
    subfams_by_fam = parse_subfams_by_fam(request.query_params, family_list)

    # total informativo
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

    years = _default_years()

    # traer TODO (sin paginación)
    products = get_products_all(
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
        years=years,         # ✅ antes year=2025
        max_rows=20000,      # ajusta si hace falta
    )

    # ventas/eta en chunks (para no hacer IN gigante)
    itmrefs = [p["ITMREF_0"] for p in products if p.get("ITMREF_0")]

    sales_rows: list[dict] = []
    eta_rows: list[dict] = []
    for chunk in _chunks(itmrefs, 500):
        sales_rows.extend(get_sales_12m(chunk))
        eta_rows.extend(get_eta_rows(chunk))

    products = format_products(products, sales_rows=sales_rows, eta_rows=eta_rows)

    # CSS inline
    base_dir = Path(__file__).resolve().parent
    cards_css = (base_dir / "static" / "css" / "zproveart" / "_cards_pdf.css").read_text("utf-8")
    pdf_css = (base_dir / "static" / "css" / "zproveart" / "pdf.css").read_text("utf-8")

    # header (Chromium permite pageNumber/totalPages con esos spans)
    header_html = templates.get_template("partials/pdf_header_playwright.html").render({
        "request": request,
        "total": total,
        "family_list": family_list,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
    })

    # CHUNK de tarjetas por “doc” (evita HTML gigantesco)
    CARDS_PER_PDF_CHUNK = 100  # prueba 40/60/80 según tamaño de cada card

    pdf_parts: list[bytes] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage", "--no-sandbox"])

        # render por bloques
        for prod_chunk in _chunks(products, CARDS_PER_PDF_CHUNK):
            html = templates.get_template("pages/zproveart_pdf.html").render({
                "request": request,
                "products": prod_chunk,
                "total": total,
                "cards_css": cards_css,
                "pdf_css": pdf_css,
            })

            pdf_parts.append(_render_pdf_chunk(browser=browser, html=html, header_html=header_html))

        browser.close()

    # unir PDFs
    pdf_bytes = _merge_pdfs(pdf_parts)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="zproveart.pdf"'},
    )


@app.get("/zproveart/pdf/html", response_class=HTMLResponse)
def zproveart_pdf_html(request: Request, family: list[str] = Query(default=[])):
    date_from = parse_date(request.query_params.get("from"))
    date_to = parse_date(request.query_params.get("to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    supp_from = request.query_params.get("supp_from")
    supp_to = request.query_params.get("supp_to")
    comp_from = request.query_params.get("comp_from")
    comp_to = request.query_params.get("comp_to")
    art_from = request.query_params.get("art_from")
    art_to = request.query_params.get("art_to")

    family_list = [str(f).strip() for f in family if f and str(f).strip()]
    subfams_by_fam = parse_subfams_by_fam(request.query_params, family_list)

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

    years = _default_years()

    products = get_products_all(
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
        years=years,    # ✅ antes year=2025
        max_rows=20000,
    )

    itmrefs = [p["ITMREF_0"] for p in products if p.get("ITMREF_0")]
    sales_rows: list[dict] = []
    eta_rows: list[dict] = []
    for chunk in _chunks(itmrefs, 500):
        sales_rows.extend(get_sales_12m(chunk))
        eta_rows.extend(get_eta_rows(chunk))

    products = format_products(products, sales_rows=sales_rows, eta_rows=eta_rows)

    base_dir = Path(__file__).resolve().parent
    cards_css = (base_dir / "static" / "css" / "zproveart" / "_cards_pdf.css").read_text("utf-8")
    pdf_css = (base_dir / "static" / "css" / "zproveart" / "pdf.css").read_text("utf-8")

    html = templates.get_template("pages/zproveart_pdf.html").render({
        "request": request,
        "products": products,
        "total": total,
        "cards_css": cards_css,
        "pdf_css": pdf_css,
    })

    return HTMLResponse(content=html)


def parse_subfams_by_fam(query_params, fams: list[str]) -> dict[str, list[str]]:
    """
    Lee params tipo subfam_12=1207&subfam_12=1208 y devuelve:
    {"12": ["1207", "1208"]}
    Solo para familias seleccionadas.
    """
    out: dict[str, list[str]] = {}
    for fam in fams:
        key = f"subfam_{fam}"
        vals = query_params.getlist(key)  # 👈 importante: getlist
        vals = [str(v).strip() for v in vals if v and str(v).strip()]
        if vals:
            out[fam] = vals
    return out


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def _merge_pdfs(pdf_list: list[bytes]) -> bytes:
    if not pdf_list:
        return b""

    # 1) Si hay PdfMerger, perfecto
    if PdfMerger is not None:
        merger = PdfMerger()
        for b in pdf_list:
            merger.append(BytesIO(b))
        out = BytesIO()
        merger.write(out)
        merger.close()
        return out.getvalue()

    # 2) Si no, usamos PdfWriter (pypdf 6.x)
    if PdfWriter is not None:
        writer = PdfWriter()
        from pypdf import PdfReader  # import aquí para asegurar disponibilidad
        for b in pdf_list:
            reader = PdfReader(BytesIO(b))
            for page in reader.pages:
                writer.add_page(page)
        out = BytesIO()
        writer.write(out)
        return out.getvalue()

    # 3) Si no hay nada, error real
    raise RuntimeError(
        "No se pudo importar pypdf correctamente. Error: "
        + repr(_pypdf_import_error)
    )


def _render_pdf_chunk(
    *,
    browser,
    html: str,
    header_html: str,
) -> bytes:
    page = browser.new_page()
    page.set_content(html, wait_until="domcontentloaded")

    # Espera a que exista el grid (ajusta selector si tu template usa otro)
    page.wait_for_selector(".pdf-grid", timeout=60000)

    # Espera imágenes (con timeout razonable)
    try:
        page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)",
            timeout=60000,
        )
    except Exception:
        # si alguna imagen no carga (404 / lenta), no bloqueamos el PDF
        pass

    return page.pdf(
        format="A4",
        landscape=True,
        print_background=True,
        display_header_footer=True,
        header_template=header_html,
        footer_template="<div></div>",
        margin={"top": "18mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
    )
