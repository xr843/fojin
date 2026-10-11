"""辞典 / 人物 SSR 页不做语言版本，但 html lang 不该谎称简体。

词条与人物正文多为繁体或原典字形，``zh-Hans`` 是错的；用不区分字形的 ``zh``。
"""

import inspect

from app.api import seo_dict, seo_persons


def test_dict_and_persons_html_lang_is_generic_zh():
    for mod in (seo_dict, seo_persons):
        src = inspect.getsource(mod)
        assert '<html lang="zh">' in src, mod.__name__
        assert '<html lang="zh-Hans">' not in src, mod.__name__
