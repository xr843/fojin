"""今日经句的两份小字体：只含经句池（繁简两套字形）里用到的字，几十 KB。

- 简体界面：马善政毛笔楷书（Ma Shan Zheng，SIL OFL 1.1，与站名「佛津」同一支毛笔体）。
  它是 GB2312 字量的字体，没有繁体字形，标点又宽又居中，所以只收汉字、不收标点；
  标点落到下面的文楷上。
- 繁体界面 + 全部标点：霞鹜文楷（LXGW WenKai，SIL OFL 1.1），繁简齐全。

改了 dailyPassages.json 就重跑本脚本；文件名带版本号（Cloudflare 按扩展名缓存 .woff2、
部署后仍会发旧文件，见 fonts.css 注释），字表变了就把 VERSION 加一。

用法（字体原文件放在 E 盘中转目录，不进仓库）：
    cd frontend && node scripts/daily_font_chars.mjs > /tmp/chars.json && cd ..
    uvx --from fonttools --with brotli --with freetype-py python backend/scripts/build_daily_fonts.py /mnt/e/transfer/fonts-daily /tmp/chars.json
"""

import ctypes
import json
import pathlib
import sys

import freetype
from fontTools import subset
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

VERSION = 1
ROOT = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend/public/fonts"
MANIFEST = ROOT / "frontend/src/data/dailyFontGlyphs.json"
PUNCT = "，。；：？！、“”「」"


# 毛笔体没有的字（「涅槃」的槃、「罣礙」的罣）：从文楷借字形，加粗、略缩到毛笔体的字面大小，
# 免得夹在毛笔字中间显得又细又大。比直接让浏览器回落到文楷协调得多（对比图看过）。
BORROW_STRENGTH = 25  # 加粗量（字体单位，UPM 1000）；70 过粗、40 偏粗，对比图定 25
BORROW_SCALE = 0.91  # 毛笔体字面约 -72..777，文楷约 -104..829


def borrow_glyphs(font: TTFont, donor_path: pathlib.Path, chars: str) -> None:
    face = freetype.Face(str(donor_path))
    cmap_tables = [t for t in font["cmap"].tables if t.isUnicode()]
    cx, cy = 500, 350
    for ch in chars:
        face.load_char(ch, freetype.FT_LOAD_NO_SCALE | freetype.FT_LOAD_NO_HINTING)
        outline = face.glyph.outline
        freetype.raw.FT_Outline_Embolden(ctypes.byref(outline._FT_Outline), BORROW_STRENGTH)
        outline = face.glyph.outline
        pen = TTGlyphPen(None)
        tp = TransformPen(pen, (BORROW_SCALE, 0, 0, BORROW_SCALE, cx * (1 - BORROW_SCALE), cy * (1 - BORROW_SCALE)))
        start = 0
        pts, tags = outline.points, outline.tags
        for end in outline.contours:
            contour = list(zip(pts[start : end + 1], tags[start : end + 1], strict=True))
            start = end + 1
            # TrueType 轮廓只有二次点：on-curve 标记位 1；起点取第一个 on-curve
            k = next(i for i, (_, t) in enumerate(contour) if t & 1)
            contour = contour[k:] + contour[:k]
            tp.moveTo(contour[0][0])
            offs = []
            for pt, tag in contour[1:]:
                if tag & 1:
                    tp.qCurveTo(*offs, pt) if offs else tp.lineTo(pt)
                    offs = []
                else:
                    offs.append(pt)
            if offs:
                tp.qCurveTo(*offs, contour[0][0])
            tp.closePath()
        name = f"borrow_{ord(ch):04X}"
        font.setGlyphOrder([*font.getGlyphOrder(), name])
        glyph = pen.glyph()
        glyph.coordinates.toInt()
        glyph.recalcBounds(font["glyf"])
        font["glyf"][name] = glyph
        font["hmtx"][name] = (1000, glyph.xMin)
        for t in cmap_tables:
            t.cmap[ord(ch)] = name
    font["maxp"].numGlyphs = len(font.getGlyphOrder())


def build(src: pathlib.Path, chars: str, out: pathlib.Path, donor: pathlib.Path | None = None) -> None:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    font = subset.load_font(str(src), opts)
    if donor is not None:
        have = font.getBestCmap()
        borrow_glyphs(font, donor, "".join(c for c in chars if ord(c) not in have))
    cmap = font.getBestCmap()
    missing = [c for c in chars if ord(c) not in cmap]
    if missing:
        sys.exit(f"{src.name} 缺字：{''.join(missing)}")
    s = subset.Subsetter(opts)
    s.populate(text=chars)
    s.subset(font)
    subset.save_font(font, str(out), opts)
    print(f"{out.name}: {len(chars)} 字, {out.stat().st_size // 1024} KB")


def main() -> None:
    src_dir = pathlib.Path(sys.argv[1])
    sets = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    chars = "".join(sorted(set(sets["simp"]) | set(sets["trad"]) | set(PUNCT)))
    brush = "".join(sorted(c for c in set(sets["simp"]) if c not in PUNCT))
    kai_src = src_dir / "LXGWWenKai-Regular.ttf"
    build(src_dir / "MaShanZheng-Regular.ttf", brush, PUBLIC / f"daily-brush-v{VERSION}.woff2", donor=kai_src)
    build(kai_src, chars, PUBLIC / f"daily-kai-v{VERSION}.woff2")
    MANIFEST.write_text(
        json.dumps({"version": VERSION, "brush": brush, "kai": chars}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
