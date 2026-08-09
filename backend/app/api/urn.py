"""HTTP endpoint that turns a fojin URN into a reader URL.

This is the public face of app.services.urn — the contract that
external citers (papers, datasets, third-party tools) can rely on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.urn import (
    URNParseError,
    absolute_reader_url,
    parse_urn,
    resolve_urn,
)

router = APIRouter(tags=["urn"])


class URNResolveResponse(BaseModel):
    urn: str
    scheme: str
    work_id: str
    juan: int | None = None
    anchor: str | None = None
    text_id: int | None = None
    # Relative path — the published contract, unchanged.
    reader_url: str | None = None
    # The same target as an absolute URL. Added because the relative form is
    # unusable to a consumer with no host: an agent holding
    # "/reader?text=42&juan=1" cannot render a link, and in practice links to
    # CBETA instead. Additive, so existing citers that prepend their own host
    # keep working.
    reader_url_absolute: str | None = None
    # True iff the work was found in the database.
    exists: bool


@router.get("/urn/resolve", response_model=URNResolveResponse)
async def urn_resolve(
    urn: str = Query(
        ...,
        min_length=8,
        max_length=300,
        description=(
            "fojin URN, e.g. `fojin:cbeta/T0001.1#p0001a01`.\n\n"
            "**Anchor (the part after `#`) must be URL-encoded as `%23` in "
            "HTTP clients**, otherwise the browser or curl will treat `#` "
            "as a fragment delimiter and strip everything after it before "
            "sending the request — the server then sees an anchor-less URN "
            "and silently returns `anchor: null`.\n\n"
            "Example (anchor preserved):\n"
            "`/api/urn/resolve?urn=fojin:cbeta/T0001.1%23p0001a01`"
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """Parse a fojin URN and return its resolution target.

    Returns 422 if the URN is syntactically invalid (parse error),
    so clients distinguish "you sent bad input" from "I can't find
    the referenced work". A valid-but-unknown URN returns 200 with
    exists=false rather than 404 so external tools can detect the
    miss without parsing an error body.
    """
    try:
        parsed = parse_urn(urn)
    except URNParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    text_id, reader_url = await resolve_urn(db, parsed)

    return URNResolveResponse(
        urn=parsed.raw,
        scheme=parsed.scheme,
        work_id=parsed.work_id,
        juan=parsed.juan,
        anchor=parsed.anchor,
        text_id=text_id,
        reader_url=reader_url,
        reader_url_absolute=absolute_reader_url(reader_url),
        exists=text_id is not None,
    )
