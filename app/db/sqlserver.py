import pyodbc

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
    return pyodbc.connect(conn_str, timeout=10)

def test_connection():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        return cursor.fetchone()[0]

def count_products() -> int:
    sql = """
    SELECT COUNT(*)
    FROM [GERIMPORT].[ZTPROVEART] AS ZTP
    WHERE COALESCE(ZTP.BPSNUM_0, '') <> '';
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return int(cur.fetchone()[0])

def get_products(page: int, page_size: int) -> list[dict]:
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
    ORDER BY ZTP.ITMREF_0 DESC
    OFFSET (@Page - 1) * @PageSize ROWS
    FETCH NEXT @PageSize ROWS ONLY;
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, [page, page_size])
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