from datetime import date


# =========================
# FORMATOS (ES)
# =========================
def _fmt_es(num: float, decimals: int = 0) -> str:
    """
    Formato español:
    - miles con '.'
    - decimales con ','
    """
    s = f"{num:,.{decimals}f}"           # 1,234,567.89
    return s.replace(",", "X").replace(".", ",").replace("X", ".")  # 1.234.567,89


def fmt_int(v) -> str:
    if v in (None, ""):
        return "-"
    try:
        vv = float(v)
    except Exception:
        return str(v)
    if abs(vv) < 1e-6:
        return "0"
    return _fmt_es(vv, 0)


def fmt_money(v) -> str:
    if v is None:
        return "-"
    try:
        return _fmt_es(float(v), 2)
    except Exception:
        return str(v)


def fmt_pct(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{_fmt_es(float(v), 2)} %"
    except Exception:
        return f"{v} %"


def fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "-"


# =========================
# CONDICIONES COMERCIALES
# =========================
def _format_condiciones_comerciales(p: dict) -> dict:
    out = dict(p)

    out["FUC_0_FMT"] = fmt_date(p.get("FUC_0"))

    for f in ("FOB_0", "PUE_0", "PVPT4_0", "DIF_0", "ARANCEL_0"):
        out[f"{f}_FMT"] = fmt_money(p.get(f))

    out["UQTY_0"] = fmt_int(p.get("UQTY_0"))
    out["DTO_0_FMT"] = fmt_pct(p.get("DTO_0"))

    return out


# =========================
# 12 MESES
# =========================
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

            ventas = ""
            compras = ""
            if r:
                if r.get("VENTAS_0") is not None:
                    ventas = _fmt_es(float(r["VENTAS_0"]), 0)
                if r.get("COMPRAS_0") is not None:
                    compras = _fmt_es(float(r["COMPRAS_0"]), 0)

            m12.append({"label": label, "ventas": ventas, "compras": compras})

        p["m12"] = m12

    return products


# =========================
# EXISTENCIAS
# =========================
def _format_existencias(p: dict) -> dict:
    out = dict(p)
    for f in ("EX_ACT_0", "EX_DISP_0", "EX_PREV_0", "QTY_PEND_SC_0"):
        out[f"{f}_FMT"] = fmt_int(p.get(f))
    return out


# =========================
# ETA / FECHAS PREVISTAS
# =========================
def _attach_eta(products: list[dict], eta_rows: list[dict], max_rows: int = 3) -> list[dict]:
    idx: dict[str, list[dict]] = {}
    for r in eta_rows:
        idx.setdefault(r["ITMREF_0"], []).append(r)

    for p in products:
        itm = p.get("ITMREF_0")
        rows = idx.get(itm, [])

        out_rows = []
        for r in rows[:max_rows]:
            out_rows.append({
                "fecha": fmt_date(r.get("FECHA_0")),
                "qty": fmt_int(r.get("QTY_0")),
                "vcr": (r.get("VCR_0") or ""),
            })

        p["eta"] = out_rows
        p["eta_extra"] = max(0, len(rows) - max_rows)

    return products

# =========================
# LOGÍSTICA
# =========================
def _format_logistica(p: dict) -> dict:
    out = dict(p)

    out["MED_PZ_0_FMT"] = p.get("MED_PZ_0") or "-"
    out["MED_CJ_0_FMT"] = p.get("MED_CJ_0") or "-"
    out["CUBIC_0_FMT"] = _fmt_es(float(p["CUBIC_0"]), 4) if p.get("CUBIC_0") else "-"

    out["UNXCAJ_0_FMT"] = fmt_int(p.get("UNXCAJ_0"))
    out["UNXPAL_0_FMT"] = fmt_int(p.get("UNXPAL_0"))
    out["UNXPAQ_0_FMT"] = fmt_int(p.get("UNXPAQ_0"))

    out["ZPUERTO_0_FMT"] = p.get("ZPUERTO_0") or "-"
    out["ZSLIM_0_FMT"] = p.get("ZSLIM_0") or "-"
    out["CMC_0_FMT"] = fmt_int(p.get("CMC_0"))

    out["ZVERNTV_0_FMT"] = "Sí" if p.get("ZVERNTV_0") in (1, "1", True) else "No"
    out["ZVTASINSTOCK_0_FMT"] = "Sí" if p.get("ZVTASINSTOCK_0") in (1, "1", True) else "No"

    out["COD_ART_PRO_0_FMT"] = p.get("COD_ART_PRO_0") or "-"

    return out

# =========================
# VALIDACIÓN ESTADO_0 OK
# =========================
def _format_estado(p: dict) -> dict:
    out = dict(p)

    estado = (p.get("ESTADO_0") or "").strip()

    out["ESTADO_0_FMT"] = estado or "-"
    out["ESTADO_OK"] = (estado == "OK")

    if not out["ESTADO_OK"]:
        out["ESTADO_MSG"] = "¡ARTÍCULO NO ACTIVO!"

    return out

# =========================
# ENTRYPOINT
# =========================
def format_products(
    products: list[dict],
    sales_rows: list[dict] | None = None,
    eta_rows: list[dict] | None = None
) -> list[dict]:

    out = []
    for p in products:
        p2 = _format_condiciones_comerciales(p)
        p2 = _format_existencias(p2)
        p2 = _format_logistica(p2)
        p2 = _format_estado(p2)
        out.append(p2)

    if sales_rows is not None:
        out = _attach_sales_12m(out, sales_rows)

    if eta_rows is not None:
        out = _attach_eta(out, eta_rows, max_rows=3)

    return out
