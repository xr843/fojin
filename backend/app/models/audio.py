from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TextAudio(Base):
    """一卷经文的一份读诵音频。

    「一份」的粒度是 (经, 卷, 语言, 音色) —— 同一卷换个音色是另一行，
    便于并存多个音色。将来若拿到授权的真人读诵，``engine`` 取 ``"human"``
    即可复用整套结构，不需改表。
    """

    __tablename__ = "text_audio"
    __table_args__ = (
        UniqueConstraint(
            "text_id", "juan_num", "lang", "voice_id",
            name="uq_text_audio_text_juan_lang_voice",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("buddhist_texts.id"), index=True, nullable=False
    )
    juan_num: Mapped[int] = mapped_column(Integer, nullable=False)
    lang: Mapped[str] = mapped_column(String(10), server_default="zh")
    # 音色标识，如 "Chinese (Mandarin)_Lyrical_Voice"
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # 合成引擎："minimax" / "azure" / "local-cosyvoice" / "human"
    engine: Mapped[str] = mapped_column(String(40), nullable=False)
    # 相对 /audio/ 的路径，文件名含 content_hash 前 8 位
    audio_path: Mapped[str] = mapped_column(String(300), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_format: Mapped[str] = mapped_column(String(10), server_default="mp3")
    char_count: Mapped[int] = mapped_column(Integer, server_default="0")
    # ⭐ 合成时所依据的 text_contents.content 的 sha256。两个用途：
    # 1. 经文被修订后音频即过期 —— 没有它，文本改了音频还在念旧的，
    #    那是「听觉上的错误信息」。
    # 2. 前 8 位进文件名：Cloudflare 边缘缓存跨部署存活，重生成后旧 URL
    #    会持续命中旧缓存；带 hash 即「重生成 = 新 URL」，永不需要 purge。
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cues: Mapped[list["TextAudioCue"]] = relationship(
        back_populates="audio", cascade="all, delete-orphan"
    )


class TextAudioCue(Base):
    """句级时间戳：音频播到 time_ms 时，正文读到 [char_start, char_end)。

    ⭐ char_start/char_end 是 text_contents.content 的 **code-point** 偏移，
    与 text_apparatus.char_start / text_line_anchors.char_offset 同一坐标系 ——
    前端已有的 cpToU16Map() 可直接复用，对齐层零成本。

    ⚠️ 不变式是 ``content[start:end].replace("\\n","") == 朗读文本``，
    **不是**逐字相等 —— 合成前抹掉了 CBETA 的行末折行（见 scripts/audio/segment.py）。

    ``kind`` 区分结构性片段（head 经名 / byline 译者署名 / juan 卷题）与
    正文（prose），前端可据此决定要不要高亮 —— 读经名时高亮标题行是对的，
    但有些界面可能只想高亮正文。
    """

    __tablename__ = "text_audio_cues"
    __table_args__ = (
        # 前端按 currentTime 二分查找当前 cue，须按时间有序整卷取出
        Index("ix_text_audio_cues_audio_time", "audio_id", "time_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("text_audio.id", ondelete="CASCADE"), nullable=False
    )
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), server_default="prose")

    audio: Mapped["TextAudio"] = relationship(back_populates="cues")
