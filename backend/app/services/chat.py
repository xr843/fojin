import asyncio
import json
import logging
import time as _time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import resolve_optional_user
from app.core.exceptions import (
    AccessDeniedError,
    QuotaExceededError,
    ServiceError,
    ValidationError,
)
from app.core.url_security import (
    create_pinned_https_transport,
    ensure_public_https_url_resolves,
)
from app.database import async_session
from app.models.chat import ChatAttachment, ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatResponse, ChatSource
from app.services.chat_quota import (  # noqa: F401
    FREE_DAILY_LIMIT_ANONYMOUS,
    FREE_DAILY_LIMIT_USER,
    _anon_quota_key,
    _check_anonymous_quota,
    _check_daily_quota,
    _validate_message,
    get_anonymous_quota_used,
)
from app.services.chat_sessions import (  # noqa: F401
    _resolve_session,
    create_session,
    delete_session,
    get_history,
    get_history_paginated,
    get_session,
    get_session_for_user,
    list_sessions,
    update_message_feedback,
)
from app.services.chat_trust import build_trust_status, persist_answer_diagnostic
from app.services.citation_guard import enforce_citation_whitelist, log_mutations

# Moved to app.services.hot_questions in the P1-3 split; re-imported here so
# `from app.services.chat import get_hot_questions` (api layer) and
# patch("app.services.chat.<name>") in tests keep working unchanged.
from app.services.hot_questions import (  # noqa: F401
    DEFAULT_HOT_QUESTIONS,
    HOT_QUESTION_CATEGORIES,
    get_hot_question_prompt,
    get_hot_questions,
    get_random_hot_questions,
)
from app.services.llm_client import (  # noqa: F401
    ANTHROPIC_API_VERSION,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_URLS,
    _build_anthropic_body,
    _build_anthropic_headers,
    _byok_error_message,
    _convert_messages_for_anthropic,
    _detect_model_from_url,
    _is_anthropic,
    _is_reasoning_model,
    _platform_provider_matches,
    _resolve_fallback_llm_config,
    _resolve_llm_config,
    _resolve_with_model_override,
    _with_reasoning_headroom,
)
from app.services.llm_cost import record_llm_cost
from app.services.master_profiles import get_master
from app.services.prompt_builder import (  # noqa: F401
    _FAILED_ANSWER_PREFIXES,
    _build_llm_messages,
    _build_reader_context_prompt,
    _build_reader_data_block,
    _classify_and_enhance_prompt,
    _estimate_tokens,
    _is_failed_answer,
    _is_meta_question,
    _strip_followup_suggestions,
)
from app.services.quote_verifier import log_quote_mutations, verify_quoted_content
from app.services.rag_retrieval import retrieve_rag_context

logger = logging.getLogger(__name__)


# SSE keepalive cadence during LLM streaming. Sized for the tightest
# documented idle-cut on the path: Cloudflare free-plan edge ≈100s,
# nginx ``proxy_read_timeout`` 120s. 25s gives ~4× headroom on both,
# while staying quiet enough that a fast-streaming model rarely emits
# a heartbeat at all. Comment-style SSE (``:\n\n``) is ignored by
# browsers per spec, so this is invisible to the frontend consumer.
LLM_STREAM_HEARTBEAT_INTERVAL_S = 25.0

# Fixed backoff before a single same-provider retry of a transient
# pre-first-token stream failure (see _stream_attempt). Kept short: the goal
# is to ride out a one-off blip (connection reset, upstream 5xx/429/timeout),
# not to wait out a sustained outage — that's what the platform fallback is
# for. No jitter: a per-request single retry doesn't need thundering-herd
# spread, and this module avoids time.monotonic-based randomness in the hot
# path.
LLM_STREAM_RETRY_BACKOFF_S = 0.5

# Provider → base URL mapping (most are OpenAI-compatible; Anthropic uses its own format)


async def _build_llm_http_client(
    api_url: str,
    provider: str,
    timeout: float,
) -> httpx.AsyncClient:
    if provider == "custom":
        transport = await create_pinned_https_transport(
            api_url,
            label="自定义 API 地址",
        )
        return httpx.AsyncClient(timeout=timeout, transport=transport)
    return httpx.AsyncClient(timeout=timeout)



def _master_scope_text_ids(master) -> list[int] | None:  # type: ignore[no-untyped-def]
    """Build the ``scope_text_ids`` value retrieve_rag_context expects.

    Asymmetric three-state contract — see also
    ``app/services/precise_retrieval.try_precise_text_retrieval`` and
    ``app/services/embedding.similarity_search`` for the consumer side:

    - ``master is None`` → return ``None``: no scope, full-corpus RAG.
    - ``master.fojin_text_ids == []`` → return ``[]``: master has no
      indexed corpus (Ajahn Chah, Hsing Yun, Yin Shun, Gampopa). The
      empty list is *deliberately preserved* — downstream
      ``similarity_search`` treats it as falsy and so leaves the
      vector path unfiltered (full-corpus RAG, the design intent),
      while ``try_precise_text_retrieval`` rejects every text_id
      against ``not in []`` and so disables precise retrieval. This
      asymmetry is the whole point: vector RAG runs across all texts
      because the master has no indexed corpus to scope against, but
      the precise short-circuit must NOT serve a 《大乘经》第N卷 query
      under a Theravada master and leak that text's chunk_text into
      the LLM's context.
    - ``master.fojin_text_ids == [ids…]`` → return the list: scoped
      vector + precise retrieval to those text_ids.

    Production trace 2026-05-07 (msg 4437): the previous
    falsy-coalesce ``master.fojin_text_ids if master and
    master.fojin_text_ids else None`` collapsed empty list → None,
    silently bypassing the precise scope check and serving 楞严经 to
    Ajahn Chah master mode. Only the persona prompt's prose refusal
    hid the breach from the user. Don't reintroduce ``or None``.
    """
    if master is None:
        return None
    return master.fojin_text_ids



async def _get_text_title(db: AsyncSession, text_id: int) -> str | None:
    """Get the Chinese title of a text by ID."""
    from app.models.text import BuddhistText
    result = await db.execute(select(BuddhistText.title_zh).where(BuddhistText.id == text_id))
    return result.scalar_one_or_none()







async def _save_messages(
    db: AsyncSession, session_id: int, message: str, answer: str, sources: list[ChatSource]
) -> int | None:
    """Persist user + assistant messages and return the assistant message's id.

    The id lets the streaming caller emit a `message_id` SSE event so the
    frontend can attach the feedback / share buttons to the real
    chat_messages row instead of the local `Date.now()` placeholder it
    used while streaming. Returns None when the message cannot be
    persisted (defensive — current callers always supply a session)."""
    # Don't persist failed/empty generations — neither the user turn nor the
    # error reply. The user saw the error live via the stream/response; saving
    # it would leave a junk turn in history and poison the answer-quality data.
    if _is_failed_answer(answer):
        return None
    user_msg = ChatMessage(session_id=session_id, role="user", content=message)
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=_strip_followup_suggestions(answer),
        sources=[s.model_dump() for s in sources] if sources else None,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)
    return assistant_msg.id


async def _generate_session_title(
    api_url: str, api_key: str, model: str, message: str, answer: str,
    *, provider: str | None = None,
) -> str | None:
    """Ask LLM to generate a short session title (5-10 chars). Returns None on failure."""
    messages = [
        {"role": "system", "content": "用5-10个中文字概括以下对话的主题，只输出标题，不要标点符号。"},
        {"role": "user", "content": f"用户问：{message[:100]}\n回答：{answer[:200]}"},
    ]
    try:
        # Route through the shared client builder so a BYOK "custom" endpoint
        # gets the same IP-pinned, rebinding-proof transport as the main chat
        # path — a bare client here would re-resolve DNS and reopen SSRF.
        async with await _build_llm_http_client(api_url, provider, 10) as client:
            if _is_anthropic(api_url, provider):
                body = _build_anthropic_body(model, messages, temperature=0.3, max_tokens=_with_reasoning_headroom(model, 64))
                resp = await client.post(f"{api_url}/messages", headers=_build_anthropic_headers(api_key), json=body)
                resp.raise_for_status()
                title = resp.json()["content"][0]["text"].strip().strip("\"'《》")
            else:
                resp = await client.post(
                    f"{api_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": _with_reasoning_headroom(model, 64)},
                )
                resp.raise_for_status()
                title = resp.json()["choices"][0]["message"]["content"].strip().strip("\"'《》")
            return title[:30] if title else None
    except Exception:
        logger.debug("Failed to generate session title, keeping default")
        return None


async def _load_and_render_attachments(
    db: AsyncSession,
    attachment_ids: list[int] | None,
    user_id: int | None,
) -> tuple[str, list[ChatAttachment]]:
    """Fetch ChatAttachment rows for the request and render them as a
    single text block prepended to the user's message.

    Ownership rules (see schemas/chat.py docstring on ``attachment_ids``):
    - logged-in user: rows where ``user_id`` matches OR is NULL (anon
      uploads are public-by-design — chat attachment uploads don't have
      an owner-binding step yet, so anyone with the id may consume).
    - anonymous user: only rows where ``user_id IS NULL``.

    Returns the rendered prefix (empty string if nothing to attach) and
    the list of attachment rows that survived the ownership filter,
    so the caller can mark them ``consumed_at`` after a successful
    LLM call.
    """
    if not attachment_ids:
        return "", []

    # Deduplicate while preserving caller order so the prompt is
    # deterministic. dict.fromkeys is the canonical idiom.
    ordered_ids = list(dict.fromkeys(attachment_ids))

    # consumed_at IS NULL makes attachments single-use: once an upload
    # has been folded into a chat message, its content can't be replayed
    # by a different caller guessing the (sequential, autoincrement) id.
    # This is the actual mitigation against anonymous-upload enumeration —
    # the user_id IS NULL allowance below is otherwise public-by-design.
    stmt = select(ChatAttachment).where(
        ChatAttachment.id.in_(ordered_ids),
        ChatAttachment.consumed_at.is_(None),
    )
    if user_id is None:
        stmt = stmt.where(ChatAttachment.user_id.is_(None))
    else:
        stmt = stmt.where(
            (ChatAttachment.user_id == user_id) | (ChatAttachment.user_id.is_(None))
        )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    # Re-sort to caller order (SQL IN doesn't guarantee order).
    by_id = {row.id: row for row in rows}
    ordered_rows = [by_id[i] for i in ordered_ids if i in by_id]
    if not ordered_rows:
        return "", []

    parts: list[str] = []
    for row in ordered_rows:
        body = row.parsed_text
        if not body:
            body = f"(解析失败：{row.parse_error or '未知错误'})"
        char_count = len(body)
        parts.append(
            f"===== 附件: {row.filename} ({char_count} 字) =====\n"
            f"{body}\n"
            f"===== 附件结束 =====\n"
        )
    return "\n".join(parts) + "\n", ordered_rows


async def _mark_attachments_consumed(
    db: AsyncSession, pending_ids: list[int]
) -> None:
    """Best-effort: stamp ``consumed_at`` on the given attachment ids so a
    future GC cron can prune orphaned uploads. Failures here must not break
    the chat response — the message is already saved by the time we get
    called.

    Takes plain ids rather than ORM rows: in the streaming path the
    attachments are loaded by ``_load_and_render_attachments`` in the
    prep-phase session, which closes (and rolls back, expiring its
    instances) before this runs (see send_message_stream's two-phase
    session split). Reading ``row.id`` / ``row.consumed_at`` on those
    detached rows raises DetachedInstanceError — caught by the try/except
    below, which would then silently SKIP the stamp and defeat the
    ``consumed_at IS NULL`` single-use mitigation that defends against
    anonymous-upload id-enumeration (see schemas/chat.py ``attachment_ids``
    docstring). Callers compute ``pending_ids`` while the rows are still
    bound. The UPDATE keeps its own ``consumed_at IS NULL`` guard so a
    concurrent consume doesn't overwrite the original timestamp.
    """
    if not pending_ids:
        return
    now = datetime.now(UTC)
    try:
        await db.execute(
            update(ChatAttachment)
            .where(ChatAttachment.id.in_(pending_ids))
            # Defensive: if another concurrent path already consumed it,
            # don't overwrite the original consumption timestamp.
            .where(ChatAttachment.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        await db.commit()
    except Exception:  # pragma: no cover — db quirks shouldn't surface to user
        logger.exception("Failed to mark attachments consumed")
        await db.rollback()


async def _prepare_chat(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
    master_id: str | None = None,
    text_id: int | None = None,
    juan_num: int | None = None,
    selected_text: str | None = None,
    page_content: str | None = None,
    hot_question_id: int | None = None,
    model_id: str | None = None,
    attachment_ids: list[int] | None = None,
) -> tuple[ChatSession | None, str, str, str, bool, str, list[ChatSource], list[dict[str, str]], list[ChatAttachment]]:
    """Shared setup for send_message and send_message_stream.

    Returns (chat_session, api_url, api_key, model, is_byok, provider, sources, llm_messages, attachments).
    chat_session is None for anonymous users. ``attachments`` is the list
    of ChatAttachment rows that were ownership-validated and prepended to
    the user message; the caller marks them ``consumed_at`` after a
    successful LLM round-trip.
    """
    _validate_message(message)

    # Hot-question shortcut: if the client sent a card id, load the structured
    # prompt template but KEEP the caller's display message for RAG / history
    # / session-title generation. Only the final LLM turn uses the template.
    llm_message_override: str | None = None
    if hot_question_id is not None:
        hq = await get_hot_question_prompt(db, hot_question_id)
        if hq is not None:
            # Client may send a stale display_text — trust the DB copy so the
            # stored history always matches the currently active card.
            message = hq[0]
            llm_message_override = hq[1]

    # Resolve session first so ownership checks (403) come before config checks (503)
    chat_session = None
    if user_id is not None:
        chat_session = await _resolve_session(db, user_id, message, session_id)

    api_url, api_key, model, is_byok, provider = _resolve_with_model_override(user, model_id)

    if not is_byok and not api_key:
        raise ServiceError("平台 AI 服务暂未配置。请在个人中心配置自己的 API Key 使用 AI 问答功能。")

    if is_byok and provider == "custom":
        try:
            api_url = await ensure_public_https_url_resolves(api_url, label="自定义 API 地址")
        except ValueError as exc:
            raise ServiceError(f"自定义 API 地址不安全：{exc}") from None

    if user_id is not None:
        if not is_byok:
            await _check_daily_quota(db, user)
    else:
        # Anonymous user — check IP-based quota via Redis
        if client_ip:
            await _check_anonymous_quota(redis, client_ip)

    # Fetch history first so we can use previous context for RAG retrieval
    history = await get_history(db, chat_session.id) if chat_session else []

    # Extract last user message from history for context-aware retrieval
    prev_user_msg = None
    for msg in reversed(history):
        if msg.role == "user":
            prev_user_msg = msg.content[:200]
            break

    # RAG: hybrid retrieval (context-aware with conversation history)
    # When a master is selected, scope RAG to their core texts
    # Skip RAG entirely for meta questions about the assistant itself
    master = get_master(master_id) if master_id else None
    if _is_meta_question(message) and not master_id and not text_id:
        sources, context_text = [], ""
    else:
        scope_text_ids = _master_scope_text_ids(master)
        sources, context_text = await retrieve_rag_context(
            db, message, prev_query=prev_user_msg, scope_text_ids=scope_text_ids,
        )

    # Reading context: enhance prompt when user is reading a specific text
    reading_context = None
    if text_id:
        text_title = await _get_text_title(db, text_id)
        if text_title:
            reading_context = {
                "title": text_title,
                "juan_num": juan_num,
                "selected_text": selected_text,
                "page_content": page_content,
            }

    # Attachments: load + ownership-check, then prepend their parsed text
    # to whatever message the LLM is going to see. We deliberately do
    # this after RAG retrieval so a 100k-char PDF doesn't pollute the
    # query embedding — the attachment is *context for the LLM answer*,
    # not a search query.
    attachment_prefix, attachments = await _load_and_render_attachments(
        db, attachment_ids, user_id,
    )
    if attachment_prefix:
        if llm_message_override is not None:
            llm_message_override = attachment_prefix + llm_message_override
        else:
            llm_message_override = attachment_prefix + message

    llm_messages = _build_llm_messages(
        history, context_text, message, master_id=master_id,
        reading_context=reading_context,
        llm_message_override=llm_message_override,
    )

    return (
        chat_session, api_url, api_key, model, is_byok, provider,
        sources, llm_messages, attachments,
    )


async def send_message(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
    master_id: str | None = None,
    text_id: int | None = None,
    juan_num: int | None = None,
    selected_text: str | None = None,
    page_content: str | None = None,
    hot_question_id: int | None = None,
    model_id: str | None = None,
    attachment_ids: list[int] | None = None,
) -> ChatResponse:
    _t0 = _time.monotonic()
    (
        chat_session, api_url, api_key, model, is_byok, provider,
        sources, llm_messages, attachments,
    ) = await _prepare_chat(
        db, user_id, message, session_id, user, client_ip=client_ip, redis=redis, master_id=master_id,
        text_id=text_id, juan_num=juan_num, selected_text=selected_text, page_content=page_content,
        hot_question_id=hot_question_id, model_id=model_id, attachment_ids=attachment_ids,
    )
    _t1 = _time.monotonic()
    logger.debug("TIMING: _prepare_chat took %.2fs", _t1 - _t0)

    # Call LLM (with fallback for platform users only)
    async def _call_once(u: str, k: str, m: str, p: str) -> str:
        client_cm = await _build_llm_http_client(u, p, 60)
        async with client_cm as client:
            if _is_anthropic(u, p):
                body = _build_anthropic_body(m, llm_messages, max_tokens=_with_reasoning_headroom(m, 8000 if page_content else 2000))
                resp = await client.post(f"{u}/messages", headers=_build_anthropic_headers(k), json=body)
                resp.raise_for_status()
                return resp.json()["content"][0]["text"]
            resp = await client.post(
                f"{u}/chat/completions",
                headers={"Authorization": f"Bearer {k}"},
                json={"model": m, "messages": llm_messages, "temperature": 0.7, "max_tokens": _with_reasoning_headroom(m, 8000 if page_content else 2000)},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    answer: str
    try:
        answer = await _call_once(api_url, api_key, model, provider)
        logger.debug("TIMING: LLM call took %.2fs", _time.monotonic() - _t1)
    except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as primary_exc:
        status = getattr(getattr(primary_exc, "response", None), "status_code", None)
        if is_byok and status in (400, 401, 403, 404, 422, 429):
            resp_body = primary_exc.response.text[:500] if isinstance(primary_exc, httpx.HTTPStatusError) and primary_exc.response else "N/A"
            logger.warning("BYOK LLM returned HTTP %s: %s | url=%s model=%s", status, resp_body, api_url, model)
            answer = _byok_error_message(primary_exc, status)
        else:
            fb = None if is_byok else _resolve_fallback_llm_config()
            if fb is not None:
                fb_url, fb_key, fb_model, fb_provider = fb
                logger.warning(
                    "Primary LLM failed (%s), falling back | primary=%s/%s fallback=%s/%s",
                    type(primary_exc).__name__, provider, model, fb_provider, fb_model,
                )
                try:
                    answer = await _call_once(fb_url, fb_key, fb_model, fb_provider)
                    # Record that this request was served by the fallback
                    api_url, api_key, model, provider = fb_url, fb_key, fb_model, fb_provider
                except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as fb_exc:
                    logger.warning("Fallback LLM also failed: %s", fb_exc)
                    answer = "抱歉，AI 服务暂时不可用，请稍后重试。"
            elif isinstance(primary_exc, httpx.TimeoutException):
                logger.warning("LLM call timed out")
                answer = "抱歉，AI 服务响应超时，请稍后重试。"
            elif isinstance(primary_exc, httpx.HTTPStatusError):
                resp_body = primary_exc.response.text[:500] if primary_exc.response else "N/A"
                logger.warning("LLM returned HTTP %s: %s | url=%s model=%s", status, resp_body, api_url, model)
                answer = f"抱歉，AI 服务返回错误（HTTP {status}），请稍后重试。"
            else:
                logger.warning("LLM request error: %s", primary_exc)
                answer = "抱歉，AI 服务暂时不可用，请稍后重试。"
    except Exception:
        logger.exception("LLM call failed")
        answer = "抱歉，AI 服务暂时不可用，请稍后重试。"

    # Citation guard: rewrite any 【《X》第N卷】 the model produced that is
    # not anchored in the retrieved sources. See app/services/citation_guard
    # for the full rationale — this is the deterministic backstop after the
    # prompt's moral one.
    #
    # Record estimated spend of the served call (platform vs BYOK) using the
    # raw answer, before the guard rewrites it. Never raises into chat.
    record_llm_cost(
        model=model, provider=provider, is_byok=is_byok,
        prompt_messages=llm_messages, completion=answer,
    )
    answer, _citation_mutations = enforce_citation_whitelist(answer, sources)
    # Quote verifier runs after the citation guard so quotes attached
    # to citations the guard already stripped don't get double-flagged.
    # See app/services/quote_verifier for the substring-match contract.
    answer, _quote_mutations = verify_quoted_content(answer, sources)
    trust_status = build_trust_status(
        answer,
        sources,
        citation_mutations=_citation_mutations,
        quote_mutations=_quote_mutations,
    )

    if chat_session:
        assistant_msg_id = await _save_messages(db, chat_session.id, message, answer, sources)
        if assistant_msg_id is not None:
            log_mutations(assistant_msg_id, _citation_mutations)
            log_quote_mutations(assistant_msg_id, _quote_mutations)
            try:
                await persist_answer_diagnostic(
                    db,
                    message_id=assistant_msg_id,
                    trust_status=trust_status,
                    citation_mutations=_citation_mutations,
                    quote_mutations=_quote_mutations,
                )
            except Exception:
                await db.rollback()
                logger.exception(
                    "Failed to persist chat answer diagnostics (message_id=%s)",
                    assistant_msg_id,
                )
        # Rows are still bound to this request session here, so reading
        # .id/.consumed_at is safe (unlike the streaming save phase).
        await _mark_attachments_consumed(
            db, [a.id for a in attachments if a.consumed_at is None]
        )

        # Auto-generate a better session title for new sessions (first message)
        if chat_session.title == message[:50]:
            title = await _generate_session_title(api_url, api_key, model, message, answer, provider=provider)
            if title:
                chat_session.title = title
                await db.commit()

    return ChatResponse(
        session_id=chat_session.id if chat_session else 0,
        message=answer,
        sources=sources,
        trust_status=trust_status,
    )


async def _interleave_heartbeat(inner_gen, heartbeat_interval: float):
    """Wrap an async generator so heartbeat markers interleave during idle gaps.

    Yields ``("content", chunk)`` for each item produced by ``inner_gen`` and
    ``("ping", None)`` whenever ``heartbeat_interval`` seconds pass without a
    new chunk. The caller is expected to translate ``ping`` into a comment-style
    SSE frame (``: keepalive\\n\\n``) so intermediate proxies see traffic and
    don't reap an idle connection.

    Why this exists: ``/chat/stream`` in reader mode (``page_content`` set)
    runs DeepSeek V4 Pro for up to 120s on a long juan. When the model pauses
    generation for tens of seconds near the end, the underlying TCP stays
    quiet, and Cloudflare's free-plan edge (~100s) or nginx
    ``proxy_read_timeout`` (120s) silently sever the connection. The frontend
    XHR sees ``onerror`` (not a clean ``done`` event) and shows the
    "网络错误，请稍后重试" toast even though the answer was almost complete.
    See ``feedback_log_before_second_guess`` and the 2026-06-09 reader-mode
    incident on T1579 juan 7.

    Exceptions from ``inner_gen`` (e.g. ``httpx.TimeoutException``) are
    re-raised on the consumer side after the producer task finishes, so the
    outer fallback / retry logic is unchanged.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def _producer():
        try:
            async for chunk in inner_gen:
                await queue.put(("content", chunk))
            await queue.put(("done", None))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # If the consumer already exited (e.g. cancelled the wrapper before
            # we got here), this put would block until the outer ``finally``
            # cancels us — which is fine, just non-obvious from this line alone.
            await queue.put(("error", exc))

    task = asyncio.create_task(_producer())
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_interval
                )
            except TimeoutError:
                yield ("ping", None)
                continue
            if kind == "done":
                return
            if kind == "error":
                raise payload  # type: ignore[misc]
            yield ("content", payload)
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass


async def send_message_stream(
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
    master_id: str | None = None,
    text_id: int | None = None,
    juan_num: int | None = None,
    selected_text: str | None = None,
    page_content: str | None = None,
    hot_question_id: int | None = None,
    model_id: str | None = None,
    attachment_ids: list[int] | None = None,
    # token: production SSE path passes the raw bearer token; the user is then
    # resolved INSIDE the prep-phase session (see Phase-1 below) instead of via
    # Depends(get_optional_user), which would pin a PG connection for the whole
    # 60-120s stream. Tests inject user_id/user directly and leave token=None.
    token: str | None = None,
    sessionmaker=async_session,
):
    """Async generator yielding SSE events for streaming chat responses.

    Yields session_id immediately after validation so the frontend gets
    a response within milliseconds, then does RAG retrieval + LLM streaming.

    **Session lifecycle**: this generator opens TWO short-lived DB sessions
    instead of holding one across the whole stream. Phase-1 (prep / RAG /
    quota) and phase-3 (save / mark consumed) each get their own session,
    and the LLM-streaming phase between them runs with no session checked
    out at all.

    The previous shape (single ``db: AsyncSession = Depends(get_db)``
    threaded through the whole generator) pinned a PG connection for the
    full 60-120s LLM-streaming window — a single user with two tabs plus
    an SEO crawler could exhaust the 10+20 pool in minutes (PR #649 +
    project_fojin_db_pool_streaming). Splitting the session here lets the
    pool churn at the rate of actual DB work (typically <1s of each
    request), not at the rate of LLM latency.

    ``sessionmaker`` defaults to the module-level ``async_session`` factory
    but is overridable for tests that want to assert no-DB-during-LLM
    behaviour with a counting wrapper. The endpoint is the only caller
    that uses the default.
    """
    # Flush Cloudflare's response buffer with a padded SSE comment (~2KB).
    yield ": " + " " * 2048 + "\n\n"

    # --- Phase 1: validation, quota, session, RAG (reuse _prepare_chat) ---
    # 立即告知前端正在检索，消除空白等待感
    yield f"data: {json.dumps({'type': 'searching', 'message': '正在检索相关经文...'}, ensure_ascii=False)}\n\n"

    # Capture the prep error (if any) so we can yield it OUTSIDE the
    # ``async with`` block — yielding inside would keep the session
    # checked out for the duration of the network write to the client,
    # defeating the point of the split.
    prep_result = None
    prep_error: Exception | None = None
    # Captured INSIDE the prep block (see below) as plain scalars so no
    # detached ORM attribute is read after the session closes.
    chat_session_id = 0
    pending_attachment_ids: list[int] = []
    async with sessionmaker() as db_prep:
        try:
            # Production SSE path: resolve the user from the raw token inside
            # THIS short-lived prep session, so no request-scoped session is
            # held across the LLM stream. Tests pass user_id/user directly
            # (token=None) and skip this. user_id is reassigned here so the
            # later prep-error / save-failure logs report the right id.
            if token is not None:
                user = await resolve_optional_user(token, db_prep)
                user_id = user.id if user else None
            # Anonymous quota keys on client_ip; logged-in users key on user_id
            # (preserves the old chat_stream behaviour of only passing the IP
            # when there is no authenticated user).
            effective_client_ip = client_ip if user is None else None
            prep_result = await _prepare_chat(
                db_prep, user_id, message, session_id, user,
                client_ip=effective_client_ip, redis=redis, master_id=master_id,
                text_id=text_id, juan_num=juan_num,
                selected_text=selected_text, page_content=page_content,
                hot_question_id=hot_question_id, model_id=model_id,
                attachment_ids=attachment_ids,
            )
            # Capture the ORM rows' plain scalar values WHILE the instances
            # are still bound to db_prep. On block exit, close() rolls back the
            # still-open prep transaction (create_session's refresh() + quota
            # flush() leave it open), and a rollback EXPIRES every instance —
            # independent of expire_on_commit=False. Any lazy attribute read
            # AFTER the block then raises DetachedInstanceError. For
            # chat_session.id that killed the SSE generator before any answer
            # or 'done' reached the client, so the frontend hung forever on
            # "正在检索经文并生成回答". The same hazard applies to the
            # attachment rows consumed in the post-stream save phase: reading
            # their .id/.consumed_at there would raise inside
            # _mark_attachments_consumed's try/except and silently skip the
            # single-use consumed_at stamp (the anti-enumeration guard). So
            # snapshot both here while still bound.
            _prep_cs = prep_result[0]
            chat_session_id = _prep_cs.id if _prep_cs else 0
            pending_attachment_ids = [
                a.id for a in prep_result[-1] if a.consumed_at is None
            ]
            # Persist prep-phase writes (the _check_daily_quota UPDATE) BEFORE
            # the block exits. Without this, close() rolls back the still-open
            # prep transaction (see the snapshot note above) and discards the
            # quota increment — making FREE_DAILY_LIMIT_USER a no-op on the
            # streaming path while the non-stream path persists it via
            # _save_messages. Scalars are already captured above, so the
            # commit's instance-expiry is harmless. Quota is the only pending
            # write here (create_session already committed; everything else in
            # _prepare_chat is SELECT-only).
            await db_prep.commit()
        except (ValidationError, QuotaExceededError, AccessDeniedError, ServiceError) as exc:
            prep_error = exc
    # db_prep is closed here — connection returned to the pool before any
    # LLM I/O begins, regardless of whether prep succeeded or surfaced an
    # app-level rejection.

    if prep_error is not None:
        # Surface app-level rejections (quota, auth, attachment ownership, RAG
        # underflow, etc.) into backend logs. The frontend already gets the
        # message via the SSE 'error' event, but server-side these used to be
        # invisible — every chat that failed at the prepare phase looked like
        # an HTTP 200 in the access log and the maintainer had no breadcrumb.
        logger.warning(
            "chat/stream prepare rejected: %s: %s (user_id=%s session_id=%s)",
            type(prep_error).__name__, prep_error, user_id, session_id,
        )
        yield f"data: {json.dumps({'type': 'error', 'message': str(prep_error)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    (
        _chat_session, api_url, api_key, model, is_byok, provider,
        sources, llm_messages, _attachments,
    ) = prep_result
    # NOTE: ``_chat_session`` and ``_attachments`` are detached here (prep
    # session closed) — never read their lazy attributes. Use the scalars
    # ``chat_session_id`` / ``pending_attachment_ids`` captured above.

    # Yield session_id immediately so frontend gets a fast response
    yield f"data: {json.dumps({'type': 'session_id', 'session_id': chat_session_id}, ensure_ascii=False)}\n\n"

    # --- Phase 3: stream LLM (with fallback on connect-before-first-token failures) ---
    async def _stream_llm_once(u: str, k: str, m: str, p: str):
        """Inner generator that yields content chunks. Raises httpx errors on failure."""
        timeout = 120 if page_content else 60
        client_cm = await _build_llm_http_client(u, p, timeout)
        if _is_anthropic(u, p):
            body = _build_anthropic_body(m, llm_messages, stream=True, max_tokens=_with_reasoning_headroom(m, 8000 if page_content else 2000))
            async with client_cm as client, client.stream(
                "POST", f"{u}/messages", headers=_build_anthropic_headers(k), json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    try:
                        chunk = json.loads(payload)
                        event_type = chunk.get("type", "")
                        if event_type == "content_block_delta":
                            content = chunk.get("delta", {}).get("text", "")
                            if content:
                                yield content
                        elif event_type == "message_stop":
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
        else:
            async with client_cm as client, client.stream(
                "POST", f"{u}/chat/completions",
                headers={"Authorization": f"Bearer {k}"},
                json={"model": m, "messages": llm_messages, "temperature": 0.7,
                      "max_tokens": _with_reasoning_headroom(m, 8000 if page_content else 2000), "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    async def _stream_attempt(u: str, k: str, m: str, p: str):
        """One provider's stream, retried ONCE on a *transient* failure that
        happens *before* any token is yielded.

        Retrying after tokens have already streamed would duplicate output, so
        we only retry while this attempt has produced nothing (``yielded`` is
        False). Only transient failures are retried — a connection reset or an
        upstream 5xx/429/timeout usually succeeds on an immediate second try;
        a 4xx (bad key, model-not-found, invalid request) will just fail again,
        so we surface it straight away. This is the only resilience a BYOK
        request gets — it has no cross-provider fallback.
        """
        retried = False
        while True:
            yielded = False
            try:
                async for chunk in _stream_llm_once(u, k, m, p):
                    yielded = True
                    yield chunk
                return
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                transient = (
                    status in (429, 500, 502, 503, 504)
                    if isinstance(exc, httpx.HTTPStatusError)
                    # TimeoutException / ConnectError / ReadError etc. are all
                    # network-level and worth one retry.
                    else True
                )
                if yielded or retried or not transient:
                    raise
                retried = True
                logger.warning(
                    "LLM stream transient failure (%s, status=%s); retrying %s/%s once after %.1fs",
                    type(exc).__name__, status, p, m, LLM_STREAM_RETRY_BACKOFF_S,
                )
                await asyncio.sleep(LLM_STREAM_RETRY_BACKOFF_S)

    # Build attempt list: primary first, then platform fallback (only for non-BYOK)
    attempts: list[tuple[str, str, str, str, bool]] = [(api_url, api_key, model, provider, False)]
    if not is_byok:
        fb = _resolve_fallback_llm_config()
        if fb is not None:
            attempts.append((fb[0], fb[1], fb[2], fb[3], True))

    full_answer = ""
    received_first_token = False
    phase2_start = _time.monotonic()
    try:
        for idx, (att_url, att_key, att_model, att_provider, is_fb) in enumerate(attempts):
            try:
                async for kind, content in _interleave_heartbeat(
                    _stream_attempt(att_url, att_key, att_model, att_provider),
                    heartbeat_interval=LLM_STREAM_HEARTBEAT_INTERVAL_S,
                ):
                    if kind == "ping":
                        # SSE comment frame — browsers ignore lines starting
                        # with ":", but the bytes keep CF/nginx from reaping
                        # the connection while the LLM pauses generation.
                        yield ": keepalive\n\n"
                        continue
                    if not received_first_token:
                        received_first_token = True
                        if is_fb:
                            logger.info(
                                "Serving via fallback LLM: %s/%s (primary %s/%s failed)",
                                att_provider, att_model, provider, model,
                            )
                    full_answer += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                # Stream completed successfully — record which model actually answered
                api_url, api_key, model, provider = att_url, att_key, att_model, att_provider
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if received_first_token:
                    logger.warning("LLM stream broke mid-stream: %s", exc)
                    error_msg = "抱歉，AI 回答中途中断，请稍后重试。"
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                    full_answer = full_answer or error_msg
                    break
                # Pre-first-token failure: try fallback if any remain
                if idx < len(attempts) - 1:
                    logger.warning(
                        "Primary LLM stream failed (%s, status=%s), trying fallback",
                        type(exc).__name__, status,
                    )
                    continue
                # Final attempt failed — surface the error
                if is_byok and status in (400, 401, 403, 404, 422, 429):
                    resp_body = exc.response.text[:500] if isinstance(exc, httpx.HTTPStatusError) and exc.response else "N/A"
                    logger.warning("BYOK LLM stream HTTP %s: %s | url=%s model=%s", status, resp_body, att_url, att_model)
                    error_msg = _byok_error_message(exc, status)
                elif isinstance(exc, httpx.TimeoutException):
                    logger.warning("LLM stream timed out")
                    error_msg = "抱歉，AI 服务响应超时，请稍后重试。"
                elif isinstance(exc, httpx.HTTPStatusError):
                    resp_body = exc.response.text[:500] if exc.response else "N/A"
                    logger.warning("LLM stream returned HTTP %s: %s | url=%s model=%s", status, resp_body, att_url, att_model)
                    error_msg = f"抱歉，AI 服务返回错误（HTTP {status}），请稍后重试。"
                else:
                    logger.warning("LLM stream request error: %s", exc)
                    error_msg = "抱歉，AI 服务暂时不可用，请稍后重试。"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                full_answer = full_answer or error_msg
    except Exception:
        logger.exception("LLM stream failed")
        error_msg = "抱歉，AI 服务暂时不可用，请稍后重试。"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
        full_answer = full_answer or error_msg

    logger.info(
        "chat/stream phase-2 LLM done in %.2fs (%d chars, session_id=%s, provider=%s)",
        _time.monotonic() - phase2_start,
        len(full_answer),
        chat_session_id,
        provider,
    )

    # Citation guard: rewrite any 【《X》第N卷】 not anchored in the
    # retrieved sources. The user has already seen the raw stream; we
    # emit a final 'citation_correction' event so the frontend can swap
    # the visible message to the corrected version, then persist only
    # the corrected version to chat_messages so reload + history are
    # canonical.
    #
    # SSE event ordering contract (must be preserved if events are
    # re-ordered later): no `token` events are emitted after
    # `citation_correction`. Frontend stream consumers in
    # frontend/src/pages/ChatPage.tsx and src/components/ReaderAIPanel.tsx
    # rely on this — once they swap the visible message to the corrected
    # text, a late `token` would re-append the LLM's raw output and
    # silently re-introduce the hallucination this guard exists to
    # prevent.
    cg_start = _time.monotonic()
    # Estimated spend of the served call (model/provider are the winning
    # attempt's after the stream loop; is_byok reflects platform vs BYOK).
    # Uses the raw full_answer, before the guard produces corrected_answer.
    record_llm_cost(
        model=model, provider=provider, is_byok=is_byok,
        prompt_messages=llm_messages, completion=full_answer,
    )
    corrected_answer, _citation_mutations = enforce_citation_whitelist(full_answer, sources)
    # Quote verifier runs after citation_guard so flagged-and-stripped
    # citations don't carry their quotes into a second annotation.
    corrected_answer, _quote_mutations = verify_quoted_content(corrected_answer, sources)
    trust_status = build_trust_status(
        corrected_answer,
        sources,
        citation_mutations=_citation_mutations,
        quote_mutations=_quote_mutations,
    )
    logger.info(
        "chat/stream phase-cg %.2fs (citations=%d, quotes=%d)",
        _time.monotonic() - cg_start,
        len(_citation_mutations),
        len(_quote_mutations),
    )
    # Emit one merged `citation_correction` event covering both
    # rewrites (citation + quote annotations) so the frontend swap is a
    # single state mutation rather than two.
    if _citation_mutations or _quote_mutations:
        yield (
            "data: "
            + json.dumps(
                {"type": "citation_correction", "content": corrected_answer},
                ensure_ascii=False,
            )
            + "\n\n"
        )

    yield (
        "data: "
        + json.dumps(
            {"type": "trust_status", "trust_status": trust_status.model_dump()},
            ensure_ascii=False,
        )
        + "\n\n"
    )

    # 回答完成后显示引用来源——先论点后论据，自然阅读顺序
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': [s.model_dump() for s in sources]}, ensure_ascii=False)}\n\n"

    # --- Phase 3: persist messages + attachments ---
    # Fresh session so LLM-stream latency above didn't pin a pool slot.
    # Captured outside the block so the resulting yield happens after the
    # session is back in the pool (same reasoning as the prep block).
    #
    # Wrapped in try/except so a save-side failure (PG transient, unique
    # violation, etc.) still lets us emit ``done`` to the client. Without
    # this, an unhandled exception would escape the generator and the
    # frontend stream consumer would never see the completion event —
    # the user got their reply but the UI sits in "thinking…" until
    # they navigate away. The reply is unfortunately not persisted in
    # this failure mode; the alternative (silently retry / different
    # storage path) is out of scope for this refactor.
    assistant_msg_id: int | None = None
    if chat_session_id:
        save_start = _time.monotonic()
        try:
            async with sessionmaker() as db_save:
                assistant_msg_id = await _save_messages(
                    db_save, chat_session_id, message, corrected_answer, sources
                )
                if assistant_msg_id is not None:
                    log_mutations(assistant_msg_id, _citation_mutations)
                    log_quote_mutations(assistant_msg_id, _quote_mutations)
                await _mark_attachments_consumed(db_save, pending_attachment_ids)
                if assistant_msg_id is not None:
                    try:
                        await persist_answer_diagnostic(
                            db_save,
                            message_id=assistant_msg_id,
                            trust_status=trust_status,
                            citation_mutations=_citation_mutations,
                            quote_mutations=_quote_mutations,
                        )
                    except Exception:
                        await db_save.rollback()
                        logger.exception(
                            "chat/stream diagnostic persist failed (message_id=%s)",
                            assistant_msg_id,
                        )
        except Exception:
            logger.exception(
                "chat/stream phase-3 save failed; user got the reply but it is "
                "not persisted (session_id=%s, user_id=%s)",
                chat_session_id, user_id,
            )
        logger.info(
            "chat/stream phase-3 save %.2fs (session_id=%s, assistant_msg_id=%s)",
            _time.monotonic() - save_start,
            chat_session_id,
            assistant_msg_id,
        )
        # db_save closed before the message_id yield below.

        # Emit the real chat_messages.id so the frontend can swap the
        # in-flight Date.now() placeholder. Without this, feedback /
        # share buttons on a freshly-streamed message PUT to a
        # nonexistent id — which is why the production feedback rate
        # has been zero despite the UI being wired in ChatPage.
        if assistant_msg_id is not None:
            yield (
                "data: "
                + json.dumps({"type": "message_id", "id": assistant_msg_id})
                + "\n\n"
            )
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


