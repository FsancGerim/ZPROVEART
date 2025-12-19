import time
from datetime import date
import pyodbc
from typing import List, Dict, Optional
pyodbc.pooling = True

from app.config import (
    SQL_SERVER,
    SQL_DB,
    SQL_USER,
    SQL_PASS,
    SQL_DRIVER,
)

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

def count_products(
    families: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    supp_from: str | None = None,
    supp_to: str | None = None,
    comp_from: str | None = None,
    comp_to: str | None = None
) -> int:
    fams = [f.strip() for f in (families or []) if f and f.strip()]

    sql = """
    SELECT COUNT(1)
    FROM ZTPROVEART AS ZTP
    WHERE ZTP.BPSNUM_0 IS NOT NULL
      AND ZTP.BPSNUM_0 <> ''
    """

    params: list = []

    if supp_from:
        sql += " AND ZTP.BPSNUM_0 >= ?\n"
        params.append(supp_from)
    if supp_to:
        sql += " AND ZTP.BPSNUM_0 <= ?\n"
        params.append(supp_to)

    if comp_from:
        sql += " AND ZTP.COD_COM_0 >= ?\n"
        params.append(comp_from)
    if comp_to:
        sql += " AND ZTP.COD_COM_0 <= ?\n"
        params.append(comp_to)

    if fams:
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
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supp_from: Optional[str] = None,
    supp_to: Optional[str] = None,
    comp_from: Optional[str] = None,
    comp_to: Optional[str] = None
) -> list[dict]:

    fams = [f.strip() for f in (families or []) if f and f.strip()]

    sql = """
    DECLARE @Page INT = ?;
    DECLARE @PageSize INT = ?;

    WITH base AS (
        SELECT
            ZTP.ITMREF_0,
            ZTP.ITMDES_0,
            ZTP.BPSNUM_0,
            ZTP.FUC_0,
            ZTP.UQTY_0, ZTP.FOB_0, ZTP.PUE_0, ZTP.PVPT4_0, ZTP.DTO_0, ZTP.DIF_0, ZTP.ARANCEL_0,
            ZTP.EX_ACT_0, ZTP.EX_DISP_0, ZTP.EX_PREV_0,
            ZTP.COD_ART_PRO_0,
            ZTP.MED_PZ_0,
            ZTP.MED_CJ_0,
            ZTP.CUBIC_0
        FROM ZTPROVEART AS ZTP
        WHERE ZTP.BPSNUM_0 IS NOT NULL
          AND ZTP.BPSNUM_0 <> ''
    """

    params: list = [page, page_size]

    if supp_from:
        sql += " AND ZTP.BPSNUM_0 >= ?\n"
        params.append(supp_from)
    if supp_to:
        sql += " AND ZTP.BPSNUM_0 <= ?\n"
        params.append(supp_to)

    if comp_from:
        sql += " AND ZTP.COD_COM_0 >= ?\n"
        params.append(comp_from)
    if comp_to:
        sql += " AND ZTP.COD_COM_0 <= ?\n"
        params.append(comp_to)

    if fams:
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

    if date_from:
        sql += " AND ZTP.FUC_0 >= ?\n"
        params.append(date_from)

    if date_to:
        sql += " AND ZTP.FUC_0 < DATEADD(DAY, 1, ?)\n"
        params.append(date_to)

    sql += """
        ORDER BY ZTP.FUC_0 DESC, ZTP.ITMREF_0 DESC
        OFFSET (@Page - 1) * @PageSize ROWS
        FETCH NEXT @PageSize ROWS ONLY
    )
    SELECT
        base.ITMREF_0, base.ITMDES_0, base.BPSNUM_0,
        ZURL.URL_0,
        base.FUC_0,
        base.UQTY_0, base.FOB_0, base.PUE_0, base.PVPT4_0, base.DTO_0, base.DIF_0, base.ARANCEL_0,
        base.EX_ACT_0, base.EX_DISP_0, base.EX_PREV_0,
        base.COD_ART_PRO_0,
        base.MED_PZ_0,
        base.MED_CJ_0,
        base.CUBIC_0,
        BPS.BPSNAM_0,
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
        Z4.ZVTASINSTOCK_0
    FROM base
    LEFT JOIN BPSUPPLIER AS BPS
        ON base.BPSNUM_0 = BPS.BPSNUM_0
    LEFT JOIN ZURLIMAGENES AS ZURL
        ON base.ITMREF_0 = ZURL.ITMREF_0
    LEFT JOIN ZPROART4 AS Z4
        ON base.ITMREF_0 = Z4.ITMREF_0
    ORDER BY base.FUC_0 DESC, base.ITMREF_0 DESC;
    """

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
    sql = f"""
    SELECT DISTINCT COD_FAM_0, DES_FAM_0
    FROM ZPROART4;
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