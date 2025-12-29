from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from urllib.parse import urlparse
import httpx

router = APIRouter()

ALLOWED_HOSTS = {"192.168.1.82"}

@router.get("/foto")
async def foto(u: str = Query(..., description="URL completa de la imagen")):
    parsed = urlparse(u)

    # Validaciones básicas para que no sea un proxy abierto
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL inválida")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail="Host no permitido")

    async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
        r = await client.get(u)
        if r.status_code != 200:
            raise HTTPException(status_code=404, detail="Foto no encontrada")

        ctype = r.headers.get("content-type", "image/jpeg")
        return StreamingResponse(r.aiter_bytes(), media_type=ctype)
