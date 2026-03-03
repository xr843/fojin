"""seed Buddhist school entities, school affiliations, and teacher lineages

Inserts ~12 school entities into kg_entities and ~80 relations
(member_of_school + teacher_of) into kg_relations.

Idempotent: checks by name_zh before inserting entities,
uses ON CONFLICT on the partial unique index for relations.

Revision ID: 0037
Revises: 0036
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── School definitions ─────────────────────────────────────────
SCHOOLS = [
    {"name_zh": "天台宗", "name_en": "Tiantai", "name_sa": "Mādhyamaka-Tiantai",
     "desc": "以《法华经》为根本经典，智顗所创立的中国佛教宗派"},
    {"name_zh": "华严宗", "name_en": "Huayan", "name_sa": "Avataṃsaka",
     "desc": "以《华严经》为根本经典，法藏集大成的中国佛教宗派"},
    {"name_zh": "法相宗", "name_en": "Faxiang (Yogācāra)", "name_sa": "Yogācāra",
     "desc": "玄奘传入中国的唯识学派，以《成唯识论》为核心"},
    {"name_zh": "三论宗", "name_en": "Sanlun (Mādhyamaka)", "name_sa": "Mādhyamaka",
     "desc": "以龙树《中论》《十二门论》及提婆《百论》为根本的中观学派"},
    {"name_zh": "禅宗", "name_en": "Chan (Zen)", "name_sa": "Dhyāna",
     "desc": "达摩传入中国的禅修传统，强调不立文字、直指人心"},
    {"name_zh": "净土宗", "name_en": "Pure Land", "name_sa": "Sukhāvatī",
     "desc": "以念佛往生西方极乐世界为修行核心的宗派"},
    {"name_zh": "律宗", "name_en": "Vinaya (Lü)", "name_sa": "Vinaya",
     "desc": "专弘戒律的宗派，道宣为中国律宗实际创始人"},
    {"name_zh": "密宗", "name_en": "Esoteric (Zhenyan)", "name_sa": "Vajrayāna",
     "desc": "以密教经典和修法为核心的宗派，唐代三大士弘传"},
    {"name_zh": "俱舍宗", "name_en": "Kośa", "name_sa": "Abhidharmakośa",
     "desc": "以世亲《俱舍论》为根本论典的部派佛教学派"},
    {"name_zh": "成实宗", "name_en": "Chengshi (Satyasiddhi)", "name_sa": "Satyasiddhi",
     "desc": "以诃梨跋摩《成实论》为根本论典的学派"},
    {"name_zh": "涅槃宗", "name_en": "Nirvāṇa School", "name_sa": "Nirvāṇa",
     "desc": "以《大般涅槃经》为根本经典的早期中国佛教学派"},
    {"name_zh": "摄论宗", "name_en": "Shelun (Mahāyānasaṃgraha)", "name_sa": "Mahāyānasaṃgraha",
     "desc": "以无著《摄大乘论》为根本论典的学派，真谛所传"},
]

# ── School affiliations: (person_name_zh, school_name_zh) ──────
AFFILIATIONS = [
    # 法相宗
    ("玄奘", "法相宗"),
    ("窺基", "法相宗"),
    # 三论宗
    ("吉藏", "三论宗"),
    ("僧肇", "三论宗"),
    ("僧叡", "三论宗"),
    ("道融", "三论宗"),
    ("道生", "三论宗"),
    # 天台宗
    ("智顗", "天台宗"),
    ("灌頂", "天台宗"),
    ("湛然", "天台宗"),
    ("慧文", "天台宗"),
    ("慧思", "天台宗"),
    # 华严宗
    ("法藏", "华严宗"),
    ("杜順", "华严宗"),
    ("智儼", "华严宗"),
    ("澄觀", "华严宗"),
    ("宗密", "华严宗"),
    # 禅宗
    ("菩提達摩", "禅宗"),
    ("慧可", "禅宗"),
    ("僧璨", "禅宗"),
    ("道信", "禅宗"),
    ("弘忍", "禅宗"),
    ("慧能", "禅宗"),
    ("神秀", "禅宗"),
    # 净土宗
    ("慧遠", "净土宗"),
    ("曇鸞", "净土宗"),
    ("道綽", "净土宗"),
    ("善導", "净土宗"),
    # 律宗
    ("道宣", "律宗"),
    # 密宗
    ("不空", "密宗"),
    ("善無畏", "密宗"),
    ("金剛智", "密宗"),
    # 涅槃宗
    ("道生", "涅槃宗"),
    # 摄论宗
    ("真諦", "摄论宗"),
]

# ── Teacher lineages: (teacher_name_zh, student_name_zh) ───────
LINEAGES = [
    # 禅宗法脉
    ("菩提達摩", "慧可"),
    ("慧可", "僧璨"),
    ("僧璨", "道信"),
    ("道信", "弘忍"),
    ("弘忍", "慧能"),
    ("弘忍", "神秀"),
    # 天台法脉
    ("慧文", "慧思"),
    ("慧思", "智顗"),
    ("智顗", "灌頂"),
    # 华严法脉
    ("杜順", "智儼"),
    ("智儼", "法藏"),
    ("法藏", "澄觀"),
    ("澄觀", "宗密"),
    # 法相法脉
    ("戒賢", "玄奘"),
    ("玄奘", "窺基"),
    # 三论法脉（鸠摩罗什门下四杰）
    ("鳩摩羅什", "僧肇"),
    ("鳩摩羅什", "僧叡"),
    ("鳩摩羅什", "道融"),
    ("鳩摩羅什", "道生"),
    # 净土法脉
    ("曇鸞", "道綽"),
    ("道綽", "善導"),
    # 密宗三大士互传
    ("善無畏", "不空"),
    ("金剛智", "不空"),
    # 律宗
    ("智首", "道宣"),
    # 跨宗派重要师承
    ("鳩摩羅什", "道生"),
    ("那連提耶舍", "闍那崛多"),
    # 早期重要师承
    ("安世高", "嚴佛調"),
    ("支婁迦讖", "支亮"),
    ("支亮", "支謙"),
    # 天台后期
    ("灌頂", "智威"),
    ("智威", "慧威"),
    ("慧威", "玄朗"),
    ("玄朗", "湛然"),
    # 华严后期
    ("宗密", "裴休"),
    # 禅宗分支 — 南宗
    ("慧能", "南嶽懷讓"),
    ("慧能", "青原行思"),
    ("南嶽懷讓", "馬祖道一"),
    ("青原行思", "石頭希遷"),
    # 唯识/瑜伽行派印度法脉
    ("彌勒", "無著"),
    ("無著", "世親"),
    ("世親", "陳那"),
    ("陳那", "護法"),
    ("護法", "戒賢"),
    # 中观学派印度法脉
    ("龍樹", "提婆"),
    ("提婆", "羅睺羅"),
]

# Source tags for provenance
SOURCE_SCHOOL = "seed:school_affiliation"
SOURCE_LINEAGE = "seed:lineage"


def _q(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    return s.replace("'", "''") if s else ""


def upgrade() -> None:
    # ── 1. Insert school entities ──
    for school in SCHOOLS:
        name_zh = _q(school["name_zh"])
        name_en = _q(school["name_en"])
        name_sa = _q(school.get("name_sa") or "")
        desc = _q(school["desc"])
        name_sa_val = f"'{name_sa}'" if school.get("name_sa") else "NULL"
        op.execute(f"""
            INSERT INTO kg_entities (entity_type, name_zh, name_en, name_sa, description)
            SELECT 'school', '{name_zh}', '{name_en}', {name_sa_val}, '{desc}'
            WHERE NOT EXISTS (
                SELECT 1 FROM kg_entities
                WHERE entity_type = 'school' AND name_zh = '{name_zh}'
            )
        """)

    # ── 2. Insert person entities that don't exist yet ──
    all_persons: set[str] = set()
    for person, _ in AFFILIATIONS:
        all_persons.add(person)
    for teacher, student in LINEAGES:
        all_persons.add(teacher)
        all_persons.add(student)

    for person_name in all_persons:
        pn = _q(person_name)
        op.execute(f"""
            INSERT INTO kg_entities (entity_type, name_zh, description)
            SELECT 'person', '{pn}', '佛教僧侣/学者'
            WHERE NOT EXISTS (
                SELECT 1 FROM kg_entities
                WHERE entity_type = 'person' AND name_zh = '{pn}'
            )
        """)

    # ── 3. Insert member_of_school relations ──
    for person_name, school_name in AFFILIATIONS:
        pn = _q(person_name)
        sn = _q(school_name)
        op.execute(f"""
            INSERT INTO kg_relations (subject_id, predicate, object_id, source, confidence)
            SELECT p.id, 'member_of_school', s.id, '{SOURCE_SCHOOL}', 1.0
            FROM kg_entities p, kg_entities s
            WHERE p.entity_type = 'person' AND p.name_zh = '{pn}'
              AND s.entity_type = 'school' AND s.name_zh = '{sn}'
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations
                  WHERE subject_id = p.id AND predicate = 'member_of_school'
                    AND object_id = s.id AND source = '{SOURCE_SCHOOL}'
              )
        """)

    # ── 4. Insert teacher_of relations ──
    for teacher_name, student_name in LINEAGES:
        tn = _q(teacher_name)
        sn = _q(student_name)
        op.execute(f"""
            INSERT INTO kg_relations (subject_id, predicate, object_id, source, confidence)
            SELECT t.id, 'teacher_of', s.id, '{SOURCE_LINEAGE}', 1.0
            FROM kg_entities t, kg_entities s
            WHERE t.entity_type = 'person' AND t.name_zh = '{tn}'
              AND s.entity_type = 'person' AND s.name_zh = '{sn}'
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations
                  WHERE subject_id = t.id AND predicate = 'teacher_of'
                    AND object_id = s.id AND source = '{SOURCE_LINEAGE}'
              )
        """)


def downgrade() -> None:
    # Remove teacher_of relations
    op.execute(f"DELETE FROM kg_relations WHERE source = '{SOURCE_LINEAGE}'")

    # Remove member_of_school relations
    op.execute(f"DELETE FROM kg_relations WHERE source = '{SOURCE_SCHOOL}'")

    # Remove school entities
    for school in SCHOOLS:
        name = _q(school["name_zh"])
        op.execute(f"DELETE FROM kg_entities WHERE entity_type = 'school' AND name_zh = '{name}'")
