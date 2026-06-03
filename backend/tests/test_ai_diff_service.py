from app.schemas.ai_diff import AiDiffChunk
from app.services.ai_diff import compute_chunks_hash


def chunk(text_id: int, juan: int, idx: int, lang: str = "lzh", text: str = "x") -> AiDiffChunk:
    return AiDiffChunk(text_id=text_id, juan_num=juan, chunk_index=idx, lang=lang, text=text)


class TestComputeChunksHash:
    def test_deterministic_for_same_input(self):
        a = [chunk(100, 1, 0), chunk(200, 1, 5)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") == compute_chunks_hash(a, "v1", "deepseek-v4-pro")

    def test_order_independent(self):
        a = [chunk(100, 1, 0), chunk(200, 1, 5)]
        b = [chunk(200, 1, 5), chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") == compute_chunks_hash(b, "v1", "deepseek-v4-pro")

    def test_text_change_changes_hash(self):
        a = [chunk(100, 1, 0, text="觀自在")]
        b = [chunk(100, 1, 0, text="观自在")]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(b, "v1", "deepseek-v4-pro")

    def test_prompt_version_changes_hash(self):
        a = [chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(a, "v2", "deepseek-v4-pro")

    def test_model_changes_hash(self):
        a = [chunk(100, 1, 0)]
        assert compute_chunks_hash(a, "v1", "deepseek-v4-pro") != compute_chunks_hash(a, "v1", "gpt-4o-mini")

    def test_returns_64_char_hex(self):
        h = compute_chunks_hash([chunk(100, 1, 0)], "v1", "deepseek-v4-pro")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
