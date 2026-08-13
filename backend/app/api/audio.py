"""读诵目录。

⚠️ 与宿主机 nginx 的 ``location /audio/``（静态 mp3 直出）**不冲突** ——
本路由挂在 ``/api`` 前缀下，路径是 ``/api/audio/available``，不以
``/audio/`` 开头，nginx 的前缀匹配落不到那条上。

单卷音频与时间戳在 ``texts.py`` 的 ``/texts/{id}/juans/{n}/audio``；
这里只回「哪些经能听」，供索引页与经典详情页共用。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.audio import list_available_audio

router = APIRouter(tags=["audio"])


class AudioJuanItem(BaseModel):
    juan_num: int
    duration_ms: int
    url: str


class AudioCatalogItem(BaseModel):
    text_id: int
    title_zh: str
    translator: str | None = None
    dynasty: str | None = None
    taisho_id: str | None = None
    # 合成引擎。前端据此标注「AI 合成朗读」——将来拿到授权的真人读诵是 "human"，
    # 那时标注必须跟着变，不能让人以为机器读的是法师读的。
    engine: str
    juan_count: int
    total_duration_ms: int
    juans: list[AudioJuanItem] = []


class AudioCatalogResponse(BaseModel):
    total: int
    items: list[AudioCatalogItem] = []


@router.get("/audio/available", response_model=AudioCatalogResponse)
async def read_available_audio(
    lang: str = Query("zh", description="正文语言"),
    db: AsyncSession = Depends(get_db),
):
    """有在线读诵音频的经，按经聚合、按总时长升序。

    列出目前可收听的经典。音频总量按设计就很小（第一期一部），故不分页。"""
    items = await list_available_audio(db, lang)
    return AudioCatalogResponse(total=len(items), items=items)
