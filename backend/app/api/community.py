"""fojin平台交流群的站内邀请接口。逻辑与安全约束见 services/community_invite.py。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.core.deps import get_current_user
from app.models.user import User
from app.services import community_invite as ci

# 不进 OpenAPI 文档：这是只对少数人开放的私人联系方式入口，没有理由在 /docs 里公示。
router = APIRouter(prefix="/community", tags=["community"], include_in_schema=False)

# 二维码是开发者的私人联系方式：任何一层缓存（浏览器、Cloudflare）都不许留。
# 地址刻意不带 .png 扩展名——Cloudflare 按扩展名缓存，带了就可能被边缘缓存住。
# nosniff 不在这里设：宿主 nginx 对 /api/ 统一加了，重复会得到两个同名头。
_NO_STORE = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
}


@router.get("/invite")
async def get_invite(request: Request, user: User = Depends(get_current_user)):
    """当前用户是否应看到邀请卡。名单外、已关闭、二维码未就位，一律 invited=false。"""
    invited = False
    if ci.is_listed(user.id) and ci.qr_present():
        dismissed = await ci.is_dismissed(getattr(request.app.state, "redis", None), user.id)
        invited = dismissed is False
    # 按用户而异的结果：任何一层缓存都不能存（缓存键不含 Authorization）。
    return JSONResponse({"invited": invited}, headers=_NO_STORE)


@router.get("/invite/qr")
async def get_invite_qr(user: User = Depends(get_current_user)):
    """开发者微信二维码，只给名单里的已登录用户。未登录 401；已登录但名单外，或二维码未就位，一律 404。"""
    qr = ci.load_qr() if ci.is_listed(user.id) else None
    if qr is None:
        raise HTTPException(status_code=404)
    body, mime = qr
    return Response(content=body, media_type=mime, headers=_NO_STORE)


@router.post("/invite/dismiss")
async def dismiss_invite(request: Request, user: User = Depends(get_current_user)):
    """「不了，谢谢」：之后不再显示（跨设备）。名单外的用户调用也只返回 ok，不留任何记录。"""
    if ci.is_listed(user.id):
        await ci.mark_dismissed(getattr(request.app.state, "redis", None), user.id)
    return {"ok": True}
