#!/usr/bin/env bash
# 多语言 SEO 上线验收：用 Googlebot UA 抓生产，逐项核对 html lang / canonical / hreflang。
# 用法：bash deploy/seo_lang_prod_check.sh [base-url]
# 见 docs/superpowers/specs/2026-10-11-i18n-seo-design.md、docs/SEO_SETUP.md §8。
set -uo pipefail
B=${1:-https://fojin.app}
UA="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
fail=0
check() { # path expected-substring
  local body
  body=$(curl -s -A "$UA" "$B$1")
  if grep -qF -- "$2" <<<"$body"; then echo "ok   $1  ⊃ $2"; else echo "FAIL $1  ⊅ $2"; fail=1; fi
}
for p in "/" "/chat" "/verify" "/sutras/heart-sutra" "/collections/huayan" "/cross-canon" "/texts/9"; do
  check "$p"              '<html lang="zh-Hans">'
  check "$p?lang=zh-Hant" '<html lang="zh-Hant">'
  check "$p?lang=en"      '<html lang="en">'
  check "$p?lang=en"      "<link rel=\"canonical\" href=\"https://fojin.app$p?lang=en\""
  check "$p"              "hreflang=\"zh-Hant\" href=\"https://fojin.app$p?lang=zh-Hant\""
done
check "/texts/9"          '般若波罗蜜多心经（般若波羅蜜多心經）'
check "/texts/9?lang=en"  'trans. '
check "/dict/%E8%88%AC%E8%8B%A5" '<html lang="zh">'
# Fetch to a variable first: with pipefail, `curl … | grep -q` reports failure on
# large files — grep exits at the first match and curl dies of SIGPIPE.
texts_xml=$(curl -s "$B/sitemap-texts-0.xml")
if grep -q 'hreflang="en"' <<<"$texts_xml"; then echo "ok   sitemap-texts xhtml:link"; else echo "FAIL sitemap-texts xhtml:link"; fail=1; fi
static_xml=$(curl -s "$B/sitemap-static.xml")
if grep -q 'href="https://fojin.app/chat?lang=zh-Hant"' <<<"$static_xml"; then echo "ok   sitemap-static xhtml:link"; else echo "FAIL sitemap-static xhtml:link"; fail=1; fi
if grep -q 'href="https://fojin.app/verify?lang=en"' <<<"$static_xml"; then echo "ok   sitemap-static /verify"; else echo "FAIL sitemap-static /verify"; fail=1; fi
exit $fail
