import time
import pyodbc
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

def count_products(families: list[str] | None = None) -> int:
    fams = [f.strip() for f in (families or []) if f and f.strip()]
    
    sql = """
    SELECT COUNT(*)
    FROM ZTPROVEART AS ZTP
    LEFT JOIN ZPROART4 AS Z4
        ON ZTP.ITMREF_0 = Z4.ITMREF_0
    WHERE COALESCE(ZTP.BPSNUM_0, '') <> ''
    """

    params = []
    if fams:
        sql += " AND Z4.COD_FAM_0 IN (" + ",".join("?" for _ in fams) + ")"
        params.extend(fams)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return int(cur.fetchone()[0])

def get_products(page: int, page_size: int, families: list[str] | None = None) -> list[dict]:
    fams = [f.strip() for f in (families or []) if f and f.strip()]

    # Base SQL (con paginación)
    sql = """
    DECLARE @Page INT = ?;
    DECLARE @PageSize INT = ?;

    SELECT
        ZTP.ITMREF_0, ZTP.ITMDES_0, ZTP.BPSNUM_0, ZURL.URL_0,
        ZTP.FUC_0, ZTP.UQTY_0, ZTP.FOB_0, ZTP.PUE_0, ZTP.PVPT4_0, ZTP.DTO_0, ZTP.DIF_0, ZTP.ARANCEL_0,
        BPS.BPSNAM_0,
        Z4.COD_FAM_0, Z4.DES_FAM_0
    FROM ZTPROVEART AS ZTP
    LEFT JOIN BPSUPPLIER AS BPS
        ON ZTP.BPSNUM_0 = BPS.BPSNUM_0
    LEFT JOIN ZURLIMAGENES AS ZURL
        ON ZTP.ITMREF_0 = ZURL.ITMREF_0
    LEFT JOIN GERIMPORT.ZPROART4 AS Z4
        ON ZTP.ITMREF_0 = Z4.ITMREF_0
    WHERE COALESCE(ZTP.BPSNUM_0, '') <> ''
    """

    params: list = [page, page_size]

    # Filtro por familias (si hay)
    if fams:
        placeholders = ",".join("?" for _ in fams)
        sql += f" AND Z4.COD_FAM_0 IN ({placeholders})\n"
        params.extend(fams)

    # Orden + paginación
    sql += """
    ORDER BY ZTP.ITMREF_0 DESC
    OFFSET (@Page - 1) * @PageSize ROWS
    FETCH NEXT @PageSize ROWS ONLY;
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