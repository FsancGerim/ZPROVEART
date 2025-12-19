from datetime import datetime, date

def _format_condiciones_comerciales(p: dict) -> dict:
    out = dict(p)

    out["FUC_0_FMT"] = (
        p["FUC_0"].strftime("%d/%m/%Y")
        if p.get("FUC_0")
        else "-"
    )

    for f in("FOB_0", "PUE_0", "PVPT4_0", "DIF_0", "ARANCEL_0"):
        v = p.get(f)
        out[f"{f}_FMT"] = f"{v:,.2f}" if v is not None else "-"

    uq = p.get("UQTY_0")    # CUESTIONES!
    out["UQTY_0"] = f"{uq:,.0f}" if uq is not None else "-"

    dto = p.get("DTO_0")
    out["DTO_0_FMT"] = f"{dto:.2f} %" if dto is not None else "-"

    return out

MESES = {
    1: "En.",
    2: "Feb.",
    3: "Mar.",
    4: "Abr.",
    5: "May.",
    6: "Jun.",
    7: "Jul.",
    8: "Ago.",
    9: "Sep.",
    10: "Oct.",
    11: "Nov.",
    12: "Dic.",
}
def _last_12_months_desc(end: date | None = None):
    end = end or date.today()
    y, m = end.year, end.month

    out = []
    for i in range(12):
        yy = y
        mm = m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append((yy, mm, MESES[mm]))

    return out

def _attach_sales_12m(products: list[dict], sales_rows: list[dict], end_date: date | None = None) -> list[dict]:
    # Index por producto+mes para rellenar los 12 meses siempre
    idx: dict[tuple[str, int], dict] = {}
    for r in sales_rows:
        y = int(r["ANNO_0"])
        m = int(r["MES_0"])
        yyyymm = y * 100 + m
        idx[(r["ITMREF_0"], yyyymm)] = r

    months = _last_12_months_desc(end_date)

    for p in products:
        itm = p.get("ITMREF_0")
        m12 = []
        for y, m, label in months:
            yyyymm = y * 100 + m
            r = idx.get((itm, yyyymm))

            m12.append({
                "label": label,
                "ventas": (f"{r['VENTAS_0']:,.0f}" if r and r.get("VENTAS_0") is not None else ""),
                "compras": (f"{r['COMPRAS_0']:,.0f}" if r and r.get("COMPRAS_0") is not None else ""),
            })

        p["m12"] = m12

    return products

def _format_existencias(p: dict) -> dict:
    out = dict(p)

    def fmt_units(v):
        if v in (None, ""):
            return "-"
        try:
            vv = float(v)
        except Exception:
            return str(v)

        if abs(vv) < 1e-6:
            return "0"

        return f"{vv:,.0f}"

    for f in ("EX_ACT_0", "EX_DISP_0", "EX_PREV_0", "QTY_PEND_SC_0"):
        out[f"{f}_FMT"] = fmt_units(p.get(f))

    return out

def _attach_eta(products: list[dict], eta_rows: list[dict], max_rows: int = 3) -> list[dict]:
    # index por ITMREF_0 -> lista de filas
    idx: dict[str, list[dict]] = {}
    for r in eta_rows:
        idx.setdefault(r["ITMREF_0"], []).append(r)

    for p in products:
        itm = p.get("ITMREF_0")
        rows = idx.get(itm, [])

        out = []
        for r in rows[:max_rows]:
            f = r.get("FECHA_0")
            qty = r.get("QTY_0")
            out.append({
                "fecha": f.strftime("%d/%m/%Y") if f else "-",
                "qty": (f"{float(qty):,.0f}" if qty is not None else "-"),
                "vcr": r.get("VCR_0") or "",
            })

        # si hay más, lo indicamos
        extra = max(0, len(rows) - max_rows)

        p["eta"] = out
        p["eta_extra"] = extra

    return products

def format_products(products: list[dict], sales_rows: list[dict] | None = None, eta_rows: list[dict] | None = None) -> list[dict]:
    out = []
    for p in products:
        p2 = _format_condiciones_comerciales(p)
        p2 = _format_existencias(p2)  
        out.append(p2)

    if sales_rows is not None:
        out = _attach_sales_12m(out, sales_rows)

    if eta_rows is not None:
        out = _attach_eta(out, eta_rows, max_rows=3)

    return out