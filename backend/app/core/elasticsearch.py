from elasticsearch import AsyncElasticsearch

from app.config import settings

es_client: AsyncElasticsearch | None = None

INDEX_NAME = "buddhist_texts"
CONTENT_INDEX_NAME = "text_contents"

# 简繁转换 + CJK 分词的自定义 filter/analyzer
_CJK_FILTERS = {
    "filter": {
        "t2s": {
            "type": "icu_transform",
            "id": "Traditional-Simplified",
        },
    },
    "analyzer": {
        "cjk_bigram": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["t2s", "cjk_bigram", "lowercase"],
        },
        "sanskrit_iast": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["asciifolding", "lowercase"],
        },
        "pali_analyzer": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["asciifolding", "lowercase"],
        },
    },
}

INDEX_SETTINGS = {
    "settings": {
        "analysis": _CJK_FILTERS,
    },
    "mappings": {
        "properties": {
            "taisho_id": {"type": "keyword"},
            "cbeta_id": {"type": "keyword"},
            "title_zh": {
                "type": "text",
                "analyzer": "cjk_bigram",
                "fields": {"raw": {"type": "keyword"}},
            },
            "title_en": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"raw": {"type": "keyword"}},
            },
            "title_sa": {"type": "text", "analyzer": "sanskrit_iast"},
            "title_bo": {"type": "text", "analyzer": "standard"},
            "title_pi": {"type": "text", "analyzer": "pali_analyzer"},
            "translator": {
                "type": "text",
                "analyzer": "cjk_bigram",
                "fields": {"raw": {"type": "keyword"}},
            },
            "dynasty": {"type": "keyword"},
            "category": {"type": "keyword"},
            "subcategory": {"type": "keyword"},
            "fascicle_count": {"type": "integer"},
            "cbeta_url": {"type": "keyword", "index": False},
            "lang": {"type": "keyword"},
            "source_code": {"type": "keyword"},
            "has_content": {"type": "boolean"},
        }
    },
}

# text_contents analysis, as live in production since 2026-10-11 (index
# text_contents_v2 behind the alias text_contents; rebuilt by
# backend/scripts/es_text_contents_join_wraps.py — keep the two in sync).
# - cjk_content joins CBETA hard line wraps between two Han characters: the
#   cjk_bigram filter never pairs characters whose offsets are not adjacent, so
#   without this every phrase spanning a wrap (「應無所住而\n生其心」) missed.
# - content.nopunct (cjk_nopunct) also drops punctuation between Han characters,
#   the same set quote_verifier strips, for punctuation-insensitive phrase recall.
CONTENT_INDEX_SETTINGS = {
    "settings": {
        "analysis": {
            "char_filter": {
                "cbeta_join_han_wraps": {
                    "type": "pattern_replace",
                    "pattern": "(?<=\\p{IsHan})[ \\t\\u3000]*\\r?\\n[ \\t\\u3000]*(?=\\p{IsHan})",
                    "replacement": "",
                },
                "cbeta_strip_han_punct": {
                    "type": "pattern_replace",
                    "pattern": (
                        "(?<=\\p{IsHan})"
                        "[\\s,.!?;:\"'()\\[\\]\\-_~`<>*，。！？、；：「」『』“”‘’《》〈〉…—（）【】·•～\\u3000]+"
                        "(?=\\p{IsHan})"
                    ),
                    "replacement": "",
                },
            },
            "filter": {
                "t2s": {
                    "type": "icu_transform",
                    "id": "Traditional-Simplified",
                },
            },
            "analyzer": {
                "cjk_content": {
                    "type": "custom",
                    "char_filter": ["cbeta_join_han_wraps"],
                    "tokenizer": "standard",
                    "filter": ["t2s", "cjk_bigram", "lowercase"],
                },
                "cjk_nopunct": {
                    "type": "custom",
                    "char_filter": ["cbeta_strip_han_punct"],
                    "tokenizer": "standard",
                    "filter": ["t2s", "cjk_bigram", "lowercase"],
                },
                "sanskrit_iast": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["asciifolding", "lowercase"],
                },
                "pali_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["asciifolding", "lowercase"],
                },
            },
        }
    },
    "mappings": {
        "properties": {
            "text_id": {"type": "integer"},
            "cbeta_id": {"type": "keyword"},
            "title_zh": {
                "type": "text",
                "analyzer": "cjk_content",
                "fields": {"raw": {"type": "keyword"}},
            },
            "translator": {"type": "keyword"},
            "dynasty": {"type": "keyword"},
            "juan_num": {"type": "integer"},
            "content": {
                "type": "text",
                "analyzer": "cjk_content",
                "term_vector": "with_positions_offsets",
                "fields": {"nopunct": {"type": "text", "analyzer": "cjk_nopunct"}},
            },
            "char_count": {"type": "integer"},
            "lang": {"type": "keyword"},
            "source_code": {"type": "keyword"},
        }
    },
}


async def init_es() -> AsyncElasticsearch:
    global es_client
    if settings.es_password:
        es_client = AsyncElasticsearch(
            settings.es_host, basic_auth=(settings.es_user, settings.es_password)
        )
    else:
        es_client = AsyncElasticsearch(settings.es_host)
    return es_client


async def close_es():
    global es_client
    if es_client:
        await es_client.close()
        es_client = None


def get_es() -> AsyncElasticsearch:
    if es_client is None:
        raise RuntimeError("Elasticsearch client not initialized")
    return es_client
