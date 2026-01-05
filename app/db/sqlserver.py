from __future__ import annotations

import time
from datetime import date
import pyodbc
from typing import Optional

pyodbc.pooling = True

from app.config import (
    SQL_SERVER,
    SQL_DB,
    SQL_USER,
    SQL_PASS,
    SQL_DRIVER,
)

def _sanitize_years(years: list[int] | None) -> list[int]:
    """
    Normaliza lista de años.
    - Si None / vacío -> devuelve [año actual, año anterior]
    - Convierte a int, elimina duplicados, ordena DESC.
    - Limita a un rango razonable para evitar basura.
    """
    y_now = date.today().year

    if not years:
        return [y_now, y_now - 1]

    out: list[int] = []
    seen = set()

    for y in years:
        try:
            yi = int(y)
        except Exception:
            continue
        if yi < 1990 or yi > (y_now + 1):
            continue
        if yi in seen:
            continue
        seen.add(yi)
        out.append(yi)

    if not out:
        return [y_now, y_now - 1]

    out.sort(reverse=True)
    return out

def get_connection():
    conn_str = (
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DB};"
        f"UID={SQL_USER};"
        f"PWD={SQL_PASS};"
        "TrustServerCertificate=yes;"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10, autocommit=True)


def test_connection():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        return cursor.fetchone()[0]


def _sanitize_list(vals: list[str] | None) -> list[str]:
    return [str(v).strip() for v in (vals or []) if v and str(v).strip()]


def _add_family_filter(sql: str, params: list, fams: list[str]) -> tuple[str, list]:
    """
    Aplica filtro por familias usando ZPROART4 (como ya tenías).
    """
    if not fams:
        return sql, params

    placeholders = ",".join("?" for _ in fams)
    sql += f"""
    AND EXISTS (
        SELECT 1
        FROM ZPROART4 AS Z4
        WHERE Z4.ITMREF_0 = ZTP.ITMREF_0
          AND Z4.COD_FAM_0 IN ({placeholders})
    )
    """
    params.extend(fams)
    return sql, params


def _add_subfams_by_fam_filter(
    sql: str,
    params: list,
    fams: list[str],
    subfams_by_fam: dict[str, list[str]] | None,
) -> tuple[str, list]:
    """
    Filtro por grupos:
      - Si una familia NO tiene subfamilias seleccionadas -> entra completa
      - Si una familia TIENE subfamilias seleccionadas -> filtra por esas subfamilias SOLO dentro de esa familia
    Se aplica sobre ZTP.TSICOD_0_0 (familia) y ZTP.TSICOD_1_0 (subfamilia).
    """
    if not fams:
        return sql, params

    subfams_by_fam = subfams_by_fam or {}

    # Normaliza (solo claves que estén en fams)
    submap: dict[str, list[str]] = {}
    for fam in fams:
        subs = _sanitize_list(subfams_by_fam.get(fam, []))
        if subs:
            submap[fam] = subs

    # Si no hay ninguna selección de subfamilias, no añadimos nada.
    if not submap:
        return sql, params

    fams_without_sub = [f for f in fams if f not in submap]

    or_parts: list[str] = []
    or_params: list = []

    # Familias completas (sin subfamilias marcadas)
    if fams_without_sub:
        placeholders = ",".join("?" for _ in fams_without_sub)
        or_parts.append(f"(ZTP.TSICOD_0_0 IN ({placeholders}))")
        or_params.extend(fams_without_sub)

    # Familias con subfamilias seleccionadas
    for fam, subs in submap.items():
        ph = ",".join("?" for _ in subs)
        or_parts.append(f"(ZTP.TSICOD_0_0 = ? AND ZTP.TSICOD_1_0 IN ({ph}))")
        or_params.append(fam)
        or_params.extend(subs)

    if or_parts:
        sql += " AND (\n      " + "\n   OR ".join(or_parts) + "\n    )\n"
        params.extend(or_params)

    return sql, params


def count_products(
    families: list[str] | None = None,
    subfams_by_fam: dict[str, list[str]] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    supp_from: str | None = None,
    supp_to: str | None = None,
    comp_from: str | None = None,
    comp_to: str | None = None,
    art_from: str | None = None,
    art_to: str | None = None,
) -> int:
    fams = _sanitize_list(families)

    sql = """
    SELECT COUNT(1)
    FROM ZTPROVEART AS ZTP
    WHERE ZTP.BPSNUM_0 IS NOT NULL
      AND ZTP.BPSNUM_0 <> ''
    """

    params: list = []

    # Rangos artículo
    if art_from:
        sql += " AND ZTP.ITMREF_0 >= ?\n"
        params.append(art_from)
    if art_to:
        sql += " AND ZTP.ITMREF_0 <= ?\n"
        params.append(art_to)

    # Rangos proveedor
    if supp_from:
        sql += " AND ZTP.BPSNUM_0 >= ?\n"
        params.append(supp_from)
    if supp_to:
        sql += " AND ZTP.BPSNUM_0 <= ?\n"
        params.append(supp_to)

    # Rangos comprador / comercial
    if comp_from:
        sql += " AND ZTP.COD_COM_0 >= ?\n"
        params.append(comp_from)
    if comp_to:
        sql += " AND ZTP.COD_COM_0 <= ?\n"
        params.append(comp_to)

    # Filtro por familias (ZPROART4)
    sql, params = _add_family_filter(sql, params, fams)

    # Filtro subfamilias por familia (grupos)
    sql, params = _add_subfams_by_fam_filter(sql, params, fams, subfams_by_fam)

    # Fechas
    if date_from:
        sql += " AND ZTP.FUC_0 >= ?\n"
        params.append(date_from)

    if date_to:
        sql += " AND ZTP.FUC_0 < DATEADD(DAY, 1, ?)\n"
        params.append(date_to)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


def get_products(
    page: int,
    page_size: int,
    families: Optional[list[str]] = None,
    subfams_by_fam: dict[str, list[str]] | None = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supp_from: Optional[str] = None,
    supp_to: Optional[str] = None,
    comp_from: Optional[str] = None,
    comp_to: Optional[str] = None,
    art_from: Optional[str] = None,
    art_to: Optional[str] = None,
    years: list[int] | None = None,
) -> list[dict]:
    """
    Listado paginado desde ZTPROVEART (base), con joins de datos auxiliares.
    ZTCOMVEN se une SUMADO por ITMREF_0 para evitar duplicados cuando usamos varios años.
    """

    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 25), 200))

    fams = _sanitize_list(families)
    years = _sanitize_years(years)
    years_ph = ",".join("?" for _ in years)

    sql = f"""
    DECLARE @Page INT = ?;
    DECLARE @PageSize INT = ?;

    WITH base AS (
        SELECT
            ZTP.ITMREF_0,
            ZTP.ITMDES_0,
            ZTP.BPSNUM_0,
            ZTP.FUC_0,
            ZTP.UQTY_0,
            ZTP.FOB_0,
            ZTP.PUE_0,
            ZTP.PVPT4_0,
            ZTP.DTO_0,
            ZTP.DIF_0,
            ZTP.ARANCEL_0,
            ZTP.EX_ACT_0,
            ZTP.EX_DISP_0,
            ZTP.EX_PREV_0,
            ZTP.COD_ART_PRO_0,
            ZTP.MED_PZ_0,
            ZTP.MED_CJ_0,
            ZTP.CUBIC_0,
            ZTP.COD_COM_0,
            ZTP.TSICOD_0_0 AS COD_FAM_ZTP,
            ZTP.TSICOD_1_0 AS COD_SUBFAM_ZTP
        FROM ZTPROVEART AS ZTP
        WHERE ZTP.BPSNUM_0 IS NOT NULL
          AND ZTP.BPSNUM_0 <> ''
    """

    params: list = [page, page_size]

    # Rangos artículo
    if art_from:
        sql += " AND ZTP.ITMREF_0 >= ?\n"
        params.append(art_from)
    if art_to:
        sql += " AND ZTP.ITMREF_0 <= ?\n"
        params.append(art_to)

    # Rangos proveedor
    if supp_from:
        sql += " AND ZTP.BPSNUM_0 >= ?\n"
        params.append(supp_from)
    if supp_to:
        sql += " AND ZTP.BPSNUM_0 <= ?\n"
        params.append(supp_to)

    # Rangos comprador / comercial
    if comp_from:
        sql += " AND ZTP.COD_COM_0 >= ?\n"
        params.append(comp_from)
    if comp_to:
        sql += " AND ZTP.COD_COM_0 <= ?\n"
        params.append(comp_to)

    # Filtro por familias (ZPROART4)
    sql, params = _add_family_filter(sql, params, fams)

    # Filtro subfamilias por familia (grupos)
    sql, params = _add_subfams_by_fam_filter(sql, params, fams, subfams_by_fam)

    # Fechas
    if date_from:
        sql += " AND ZTP.FUC_0 >= ?\n"
        params.append(date_from)
    if date_to:
        sql += " AND ZTP.FUC_0 < DATEADD(DAY, 1, ?)\n"
        params.append(date_to)

    # Cierre CTE + paginación
    sql += f"""
        ORDER BY ZTP.FUC_0 DESC, ZTP.ITMREF_0 DESC
        OFFSET (@Page - 1) * @PageSize ROWS
        FETCH NEXT @PageSize ROWS ONLY
    )
    SELECT
        base.ITMREF_0,
        base.ITMDES_0,
        base.BPSNUM_0,
        ZURL.URL_0,
        base.FUC_0,
        base.UQTY_0,
        base.FOB_0,
        base.PUE_0,
        base.PVPT4_0,
        base.DTO_0,
        base.DIF_0,
        base.ARANCEL_0,
        base.EX_ACT_0,
        base.EX_DISP_0,
        base.EX_PREV_0,
        base.COD_ART_PRO_0,
        base.MED_PZ_0,
        base.MED_CJ_0,
        base.CUBIC_0,
        base.COD_COM_0,

        base.COD_FAM_ZTP,
        base.COD_SUBFAM_ZTP,

        BPS.BPSNAM_0,
        BPS.ZFRECUPED_0,
        BPS.ZNUMPALMIN_0,
        BPS.ZPLAZOENTRE_0,
        BPS.ZIMPMINPED_0,
        BPS.ZVOLMINCOM_0,

        Z4.COD_FAM_0,
        Z4.DES_FAM_0,
        Z4.QTY_PEND_SC_0,
        Z4.UNXCAJ_0,
        Z4.UNXPAL_0,
        Z4.UNXPAQ_0,
        Z4.ZPUERTO_0,
        Z4.ZSLIM_0,
        Z4.CMC_0,
        Z4.ZVERNTV_0,
        Z4.ZVTASINSTOCK_0,
        Z4.ESTADO_0,

        ZTCV.NUM_CLIENTES_0,
        ZTCV.NUM_ENTRADAS_0,
        ZTCV.NUM_VENTAS_0,
        ZTCV.NUM_OCU_0

    FROM base
    LEFT JOIN BPSUPPLIER AS BPS
        ON base.BPSNUM_0 = BPS.BPSNUM_0
    LEFT JOIN ZURLIMAGENES AS ZURL
        ON base.ITMREF_0 = ZURL.ITMREF_0
    LEFT JOIN ZPROART4 AS Z4
        ON base.ITMREF_0 = Z4.ITMREF_0

    LEFT JOIN (
        SELECT
            ITMREF_0,
            SUM(NUM_CLIENTES_0) AS NUM_CLIENTES_0,
            SUM(NUM_ENTRADAS_0) AS NUM_ENTRADAS_0,
            SUM(NUM_VENTAS_0)   AS NUM_VENTAS_0,
            SUM(NUM_OCU_0)      AS NUM_OCU_0
        FROM ZTCOMVEN
        WHERE ANNO_0 IN ({years_ph})
        GROUP BY ITMREF_0
    ) AS ZTCV
        ON base.ITMREF_0 = ZTCV.ITMREF_0

    ORDER BY base.FUC_0 DESC, base.ITMREF_0 DESC;
    """

    # años al final (para el subquery)
    params.extend(years)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_sales_12m(itmrefs: list[str]) -> list[dict]:
    if not itmrefs:
        return []

    placeholders = ",".join("?" for _ in itmrefs)

    sql = f"""
    SELECT
        ITMREF_0,
        ANNO_0,
        MES_0,
        COMPRAS_0,
        VENTAS_0
    FROM ZCOMVENMES
    WHERE ITMREF_0 IN ({placeholders})
      AND DATEFROMPARTS(ANNO_0, MES_0, 1) >= DATEADD(
            MONTH, -11,
            DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
          )
      AND DATEFROMPARTS(ANNO_0, MES_0, 1) <  DATEADD(
            MONTH, 1,
            DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
          )
    ORDER BY ITMREF_0, ANNO_0 DESC, MES_0 DESC;
    """

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, itmrefs)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# BLOQUE DE OBTENER FAMILIAS CON CACHÉ
def _get_fams_distinct() -> list[dict]:
    sql = """
    SELECT COD_FAM_0, DES_FAM_0
    FROM (
        SELECT DISTINCT COD_FAM_0, DES_FAM_0
        FROM ZPROART4
    ) AS x
    ORDER BY
        CASE WHEN TRY_CONVERT(INT, COD_FAM_0) IS NULL THEN 1 ELSE 0 END,
        TRY_CONVERT(INT, COD_FAM_0),
        COD_FAM_0;
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


_FAMS_CACHE = {"ts": 0.0, "data": []}
_FAMS_TTL = 60 * 10  # 10 minutos en caché


def get_fams_cached() -> list[dict]:
    now = time.time()
    if _FAMS_CACHE["data"] and (now - _FAMS_CACHE["ts"]) < _FAMS_TTL:
        return _FAMS_CACHE["data"]

    data = _get_fams_distinct()
    _FAMS_CACHE["data"] = data
    _FAMS_CACHE["ts"] = now
    return data


def _get_subfams_by_fam(cod_fam: str) -> list[dict]:
    """
    Devuelve subfamilias de una familia con su descripción.
    La descripción SIEMPRE cuelga de IDENT1_0 = '21' en ATABDIV.
    """
    IDENT1_FIXED = "21"

    sql = """
    ;WITH sub AS (
        SELECT DISTINCT
            RIGHT('0000' + LTRIM(RTRIM(ZTP.TSICOD_1_0)), 4) AS COD_SUBFAM
        FROM ZTPROVEART AS ZTP
        WHERE ZTP.TSICOD_0_0 = ?
          AND ZTP.TSICOD_1_0 IS NOT NULL
          AND LTRIM(RTRIM(ZTP.TSICOD_1_0)) <> ''
    )
    SELECT
        sub.COD_SUBFAM,
        ATX.TEXTE_0 AS DES_SUBFAM
    FROM sub
    LEFT JOIN GERIMPORT.ATEXTRA AS ATX
      ON ATX.CODFIC_0 = 'ATABDIV'
     AND ATX.ZONE_0   = 'LNGDES'
     AND ATX.LANGUE_0 = 'SPA'
     AND ATX.IDENT1_0 = ?
     AND ATX.IDENT2_0 = sub.COD_SUBFAM
    ORDER BY
        CASE WHEN TRY_CONVERT(INT, sub.COD_SUBFAM) IS NULL THEN 1 ELSE 0 END,
        TRY_CONVERT(INT, sub.COD_SUBFAM),
        sub.COD_SUBFAM;
    """

    with get_connection() as conn:
        cur = conn.cursor()
        # cod_fam → filtra ZTPROVEART
        # IDENT1_FIXED → ATABDIV 
        cur.execute(sql, [cod_fam, IDENT1_FIXED])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]



_SUBFAMS_CACHE: dict[str, dict] = {}
_SUBFAMS_TTL = 60 * 10


def get_subfams_cached(cod_fam: str) -> list[dict]:
    cod_fam = (cod_fam or "").strip()
    if not cod_fam:
        return []

    now = time.time()
    entry = _SUBFAMS_CACHE.get(cod_fam)
    if entry and entry["data"] and (now - entry["ts"]) < _SUBFAMS_TTL:
        return entry["data"]

    data = _get_subfams_by_fam(cod_fam)
    _SUBFAMS_CACHE[cod_fam] = {"ts": now, "data": data}
    return data


def get_eta_rows(itmrefs: list[str]) -> list[dict]:
    if not itmrefs:
        return []

    placeholders = ",".join("?" for _ in itmrefs)

    sql = f"""
    SELECT
        ITMREF_0,
        FECHA_0,
        QTY_0,
        VCR_0
    FROM ZPROART3
    WHERE ITMREF_0 IN ({placeholders})
      AND FECHA_0 IS NOT NULL
    ORDER BY ITMREF_0, FECHA_0 ASC;
    """

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, itmrefs)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_products_all(
    families: Optional[list[str]] = None,
    subfams_by_fam: dict[str, list[str]] | None = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supp_from: Optional[str] = None,
    supp_to: Optional[str] = None,
    comp_from: Optional[str] = None,
    comp_to: Optional[str] = None,
    art_from: Optional[str] = None,
    art_to: Optional[str] = None,
    years: list[int] | None = None,
    max_rows: int = 5000,  # safety (ajusta)
) -> list[dict]:
    """
    Listado SIN paginación desde ZTPROVEART (para PDF).
    max_rows es un cinturón de seguridad.
    ZTCOMVEN se une SUMADO por ITMREF_0 para evitar duplicados cuando usamos varios años.
    """

    fams = _sanitize_list(families)
    max_rows = max(1, min(int(max_rows or 5000), 50000))

    years = _sanitize_years(years)
    years_ph = ",".join("?" for _ in years)

    sql = f"""
    WITH base AS (
        SELECT TOP (?)
            ZTP.ITMREF_0,
            ZTP.ITMDES_0,
            ZTP.BPSNUM_0,
            ZTP.FUC_0,
            ZTP.UQTY_0,
            ZTP.FOB_0,
            ZTP.PUE_0,
            ZTP.PVPT4_0,
            ZTP.DTO_0,
            ZTP.DIF_0,
            ZTP.ARANCEL_0,
            ZTP.EX_ACT_0,
            ZTP.EX_DISP_0,
            ZTP.EX_PREV_0,
            ZTP.COD_ART_PRO_0,
            ZTP.MED_PZ_0,
            ZTP.MED_CJ_0,
            ZTP.CUBIC_0,
            ZTP.COD_COM_0,
            ZTP.TSICOD_0_0 AS COD_FAM_ZTP,
            ZTP.TSICOD_1_0 AS COD_SUBFAM_ZTP
        FROM ZTPROVEART AS ZTP
        WHERE ZTP.BPSNUM_0 IS NOT NULL
          AND ZTP.BPSNUM_0 <> ''
    """

    params: list = [max_rows]

    # Rangos artículo
    if art_from:
        sql += " AND ZTP.ITMREF_0 >= ?\n"
        params.append(art_from)
    if art_to:
        sql += " AND ZTP.ITMREF_0 <= ?\n"
        params.append(art_to)

    # Rangos proveedor
    if supp_from:
        sql += " AND ZTP.BPSNUM_0 >= ?\n"
        params.append(supp_from)
    if supp_to:
        sql += " AND ZTP.BPSNUM_0 <= ?\n"
        params.append(supp_to)

    # Rangos comprador / comercial
    if comp_from:
        sql += " AND ZTP.COD_COM_0 >= ?\n"
        params.append(comp_from)
    if comp_to:
        sql += " AND ZTP.COD_COM_0 <= ?\n"
        params.append(comp_to)

    # Filtro por familias (ZPROART4)
    sql, params = _add_family_filter(sql, params, fams)

    # Filtro subfamilias por familia (grupos)
    sql, params = _add_subfams_by_fam_filter(sql, params, fams, subfams_by_fam)

    # Fechas
    if date_from:
        sql += " AND ZTP.FUC_0 >= ?\n"
        params.append(date_from)
    if date_to:
        sql += " AND ZTP.FUC_0 < DATEADD(DAY, 1, ?)\n"
        params.append(date_to)

    sql += f"""
        ORDER BY ZTP.FUC_0 DESC, ZTP.ITMREF_0 DESC
    )
    SELECT
        base.ITMREF_0,
        base.ITMDES_0,
        base.BPSNUM_0,
        ZURL.URL_0,
        base.FUC_0,
        base.UQTY_0,
        base.FOB_0,
        base.PUE_0,
        base.PVPT4_0,
        base.DTO_0,
        base.DIF_0,
        base.ARANCEL_0,
        base.EX_ACT_0,
        base.EX_DISP_0,
        base.EX_PREV_0,
        base.COD_ART_PRO_0,
        base.MED_PZ_0,
        base.MED_CJ_0,
        base.CUBIC_0,
        base.COD_COM_0,

        base.COD_FAM_ZTP,
        base.COD_SUBFAM_ZTP,

        BPS.BPSNAM_0,
        BPS.ZFRECUPED_0,
        BPS.ZNUMPALMIN_0,
        BPS.ZPLAZOENTRE_0,
        BPS.ZIMPMINPED_0,
        BPS.ZVOLMINCOM_0,

        Z4.COD_FAM_0,
        Z4.DES_FAM_0,
        Z4.QTY_PEND_SC_0,
        Z4.UNXCAJ_0,
        Z4.UNXPAL_0,
        Z4.UNXPAQ_0,
        Z4.ZPUERTO_0,
        Z4.ZSLIM_0,
        Z4.CMC_0,
        Z4.ZVERNTV_0,
        Z4.ZVTASINSTOCK_0,
        Z4.ESTADO_0,

        ZTCV.NUM_CLIENTES_0,
        ZTCV.NUM_ENTRADAS_0,
        ZTCV.NUM_VENTAS_0,
        ZTCV.NUM_OCU_0

    FROM base
    LEFT JOIN BPSUPPLIER AS BPS
        ON base.BPSNUM_0 = BPS.BPSNUM_0
    LEFT JOIN ZURLIMAGENES AS ZURL
        ON base.ITMREF_0 = ZURL.ITMREF_0
    LEFT JOIN ZPROART4 AS Z4
        ON base.ITMREF_0 = Z4.ITMREF_0

    LEFT JOIN (
        SELECT
            ITMREF_0,
            SUM(NUM_CLIENTES_0) AS NUM_CLIENTES_0,
            SUM(NUM_ENTRADAS_0) AS NUM_ENTRADAS_0,
            SUM(NUM_VENTAS_0)   AS NUM_VENTAS_0,
            SUM(NUM_OCU_0)      AS NUM_OCU_0
        FROM ZTCOMVEN
        WHERE ANNO_0 IN ({years_ph})
        GROUP BY ITMREF_0
    ) AS ZTCV
        ON base.ITMREF_0 = ZTCV.ITMREF_0

    ORDER BY base.FUC_0 DESC, base.ITMREF_0 DESC;
    """

    params.extend(years)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

