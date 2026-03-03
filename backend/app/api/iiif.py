from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.iiif import IIIFManifestResponse
from app.services.iiif import get_manifest_by_id, get_manifest_json, get_text_manifests

router = APIRouter(prefix="/iiif", tags=["iiif"])


@router.get("/texts/{text_id}/manifests", response_model=list[IIIFManifestResponse])
async def list_text_manifests(text_id: int, db: AsyncSession = Depends(get_db)):
    manifests = await get_text_manifests(db, text_id)
    return manifests


@router.get("/manifests/{manifest_id}", response_model=IIIFManifestResponse)
async def get_manifest(manifest_id: int, db: AsyncSession = Depends(get_db)):
    manifest = await get_manifest_by_id(db, manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest 未找到")
    return manifest


@router.get("/manifests/{manifest_id}/proxy")
async def proxy_manifest(manifest_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Proxy external IIIF manifests with Redis caching."""
    redis_client = getattr(request.app.state, "redis", None)
    data = await get_manifest_json(db, manifest_id, redis_client)
    if not data:
        raise HTTPException(status_code=404, detail="Manifest 数据获取失败")
    return data
