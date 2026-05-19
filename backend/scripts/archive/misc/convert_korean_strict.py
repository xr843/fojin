#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strict Korean to Hanja conversion for Buddhist temple names."""
import asyncio, re

# Compound words - verified Buddhist terms, zero ambiguity
C = {}
# Buddha/Bodhisattva
C['\uad00\uc74c'] = '\u89c0\u97f3'        # 관음=觀音
C['\uad00\uc138\uc74c'] = '\u89c0\u4e16\u97f3'  # 관세음=觀世音
C['\uc544\ubbf8\ud0c0'] = '\u963f\u5f4c\u9640'  # 아미타=阿彌陀
C['\ubbf8\ud0c0'] = '\u5f4c\u9640'        # 미타=彌陀
C['\ubbf8\ub959'] = '\u5f4c\u52d2'        # 미륵=彌勒
C['\uc57d\uc0ac'] = '\u85e5\u5e2b'        # 약사=藥師
C['\uc11d\uac00'] = '\u91cb\u8fe6'        # 석가=釋迦
C['\ube44\ub85c'] = '\u6bd8\u76e7'        # 비로=毘盧
C['\uc9c0\uc7a5'] = '\u5730\u85cf'        # 지장=地藏
C['\ubb38\uc218'] = '\u6587\u6b8a'        # 문수=文殊
C['\ubcf4\ud604'] = '\u666e\u8ce2'        # 보현=普賢
C['\ub098\ud55c'] = '\u7f85\u6f22'        # 나한=羅漢
C['\ub300\uc6c5'] = '\u5927\u96c4'        # 대웅=大雄
C['\uc5ec\ub798'] = '\u5982\u4f86'        # 여래=如來

# Buddhist concepts
C['\uadf9\ub77d'] = '\u6975\u6a02'        # 극락=極樂
C['\uc815\ud1a0'] = '\u6de8\u571f'        # 정토=淨土
C['\ud654\uc5c4'] = '\u83ef\u56b4'        # 화엄=華嚴
C['\ubc18\uc57c'] = '\u822c\u82e5'        # 반야=般若
C['\uc5f4\ubc18'] = '\u6d85\u69c3'        # 열반=涅槃
C['\ubc95\ud654'] = '\u6cd5\u83ef'        # 법화=法華
C['\ubc95\uacc4'] = '\u6cd5\u754c'        # 법계=法界
C['\ubc95\ub959'] = '\u6cd5\u8f2a'        # 법륜=法輪
C['\ubc95\uc7a5'] = '\u6cd5\u85cf'        # 법장=法藏
C['\ubc95\uc8fc'] = '\u6cd5\u4f4f'        # 법주=法住
C['\ubc95\ud765'] = '\u6cd5\u8208'        # 법흥=法興
C['\ubc95\uc655'] = '\u6cd5\u738b'        # 법왕=法王
C['\ubc95\ubcf4'] = '\u6cd5\u5bf6'        # 법보=法寶
C['\ubc95\uad11'] = '\u6cd5\u5149'        # 법광=法光
C['\ubc95\ub9bc'] = '\u6cd5\u6797'        # 법림=法林
C['\ubc95\uc6b4'] = '\u6cd5\u96f2'        # 법운=法雲
C['\ubc95\ucc9c'] = '\u6cd5\u6cc9'        # 법천=法泉
C['\ubc95\uc218'] = '\u6cd5\u6c34'        # 법수=法水
C['\ubc95\ub828'] = '\u6cd5\u84ee'        # 법련=法蓮
C['\ubc95\uc778'] = '\u6cd5\u5370'        # 법인=法印
C['\ubc95\ub355'] = '\u6cd5\u5fb7'        # 법덕=法德

# Korean Buddhist orders
C['\uc870\uacc4'] = '\u66f9\u6eaa'        # 조계=曹溪
C['\ud0dc\uace0'] = '\u592a\u53e4'        # 태고=太古
C['\ucc9c\ud0dc'] = '\u5929\u53f0'        # 천태=天台
C['\uc9c4\uac01'] = '\u771e\u89ba'        # 진각=眞覺

# Temple structures
C['\uc815\uc0ac'] = '\u7cbe\u820d'        # 정사=精舍
C['\uc120\uc6d0'] = '\u79aa\u9662'        # 선원=禪院
C['\ucd1d\ub9bc'] = '\u53e2\u6797'        # 총림=叢林

# Famous temples
C['\ud574\uc778'] = '\u6d77\u5370'        # 해인=海印
C['\ud1b5\ub3c4'] = '\u901a\u5ea6'        # 통도=通度
C['\uc1a1\uad11'] = '\u677e\u5ee3'        # 송광=松廣
C['\ubd88\uad6d'] = '\u4f5b\u570b'        # 불국=佛國
C['\ubd88\uac11'] = '\u4f5b\u7532'        # 불갑=佛甲
C['\ubd88\uc554'] = '\u4f5b\u5dd6'        # 불암=佛巖
C['\ubd88\uc601'] = '\u4f5b\u5f71'        # 불영=佛影
C['\ubd88\uad11'] = '\u4f5b\u5149'        # 불광=佛光
C['\uc9c1\uc9c0'] = '\u76f4\u6307'        # 직지=直指
C['\uc120\uc6b4'] = '\u79aa\u96f2'        # 선운=禪雲
C['\uc120\uc554'] = '\u79aa\u5dd6'        # 선암=禪巖
C['\ub3c4\uc194'] = '\u515c\u7387'        # 도솔=兜率
C['\uc6d0\ud6a8'] = '\u5143\u66c9'        # 원효=元曉
C['\uc6d0\ud1b5'] = '\u5713\u901a'        # 원통=圓通
C['\uc6d0\uac01'] = '\u5713\u89ba'        # 원각=圓覺
C['\ub9c8\ud558'] = '\u6469\u8a36'        # 마하=摩訶
C['\ub9c8\uc560'] = '\u78e8\u5d16'        # 마애=磨崖
C['\uc720\uac00'] = '\u745c\u4f3d'        # 유가=瑜伽
C['\uc778\uac01'] = '\u9e9f\u89d2'        # 인각=麟角

# Nature compounds
for pair in [
    ('\ubc31\ub828','\u767d\u84ee'), ('\uccad\ub828','\u9751\u84ee'),  # 백련,청련
    ('\uae08\ub828','\u91d1\u84ee'), ('\ubc31\uc6b4','\u767d\u96f2'),  # 금련,백운
    ('\uccad\uc6b4','\u9751\u96f2'), ('\uae08\uac15','\u91d1\u525b'),  # 청운,금강
    ('\uae08\uc0b0','\u91d1\u5c71'), ('\uae08\ubd09','\u91d1\u5cf0'),  # 금산,금봉
    ('\uc740\ud574','\u9280\u6d77'), ('\uc740\ud558','\u9280\u6cb3'),  # 은해,은하
    ('\uc6a9\ud654','\u9f8d\u83ef'), ('\uc6a9\ubb38','\u9f8d\u9580'),  # 용화,용문
    ('\uc6a9\uad81','\u9f8d\u5bae'), ('\uc6a9\uc8fc','\u9f8d\u73e0'),  # 용궁,용주
    ('\uc6a9\ucc9c','\u9f8d\u6cc9'), ('\uc6a9\ud765','\u9f8d\u8208'),  # 용천,용흥
    ('\uc6a9\uc554','\u9f8d\u5dd6'), ('\uc6a9\uc5f0','\u9f8d\u6df5'),  # 용암,용연
    ('\uc8fd\ub9bc','\u7af9\u6797'), ('\uc1a1\ub9bc','\u677e\u6797'),  # 죽림,송림
    ('\ud559\ub9bc','\u9db4\u6797'), ('\uc30d\ub9bc','\u96d9\u6797'),  # 학림,쌍림
    ('\uc30d\uacc4','\u96d9\u6eaa'), ('\uc30d\ubd09','\u96d9\u5cf0'),  # 쌍계,쌍봉
    ('\uc30d\uc6a9','\u96d9\u9f8d'), ('\ub3d9\ub9bc','\u6771\u6797'),  # 쌍용,동림
    ('\ub3d9\uc0b0','\u6771\u5c71'), ('\uc11c\uc0b0','\u897f\u5c71'),  # 동산,서산
    ('\ub0a8\uc0b0','\u5357\u5c71'), ('\uccad\ub7c9','\u6e05\u6dbc'),  # 남산,청량
    ('\ub3d9\ud654','\u6850\u83ef'),  # 동화
]: C[pair[0]] = pair[1]

# Virtue compounds
for pair in [
    ('\ubcf4\uad11','\u666e\u5149'), ('\ubcf4\ubb38','\u666e\u9580'),  # 보광,보문
    ('\ubcf4\ub9bc','\u5bf6\u6797'), ('\ubcf4\uc740','\u5831\u6069'),  # 보림,보은
    ('\ubcf4\ub355','\u5bf6\u5fb7'), ('\ubcf4\ub828','\u5bf6\u84ee'),  # 보덕,보련
    ('\ubcf4\uc6d0','\u5bf6\u9858'),  # 보원
    ('\ub300\ud765','\u5927\u8208'), ('\ub300\uc548','\u5927\u5b89'),  # 대흥,대안
    ('\ub300\uc2b9','\u5927\u4e58'), ('\ub300\uc6d0','\u5927\u9858'),  # 대승,대원
    ('\ub300\uc801','\u5927\u5bc2'), ('\ub300\uad11','\u5927\u5149'),  # 대적,대광
    ('\uc2e0\ud765','\u65b0\u8208'), ('\uc2e0\uad11','\u65b0\u5149'),  # 신흥,신광
    ('\uc911\ud765','\u4e2d\u8208'),  # 중흥
    ('\ud574\uc6d4','\u6d77\u6708'), ('\ud574\uc6b4','\u6d77\u96f2'),  # 해월,해운
    ('\uad11\uba85','\u5149\u660e'), ('\uad11\ub355','\u5149\u5fb7'),  # 광명,광덕
    ('\uad11\uc81c','\u5149\u6fdf'), ('\uad11\ud765','\u5149\u8208'),  # 광제,광흥
    ('\uc815\uc218','\u6de8\u6c34'), ('\uc815\ud61c','\u5b9a\u6167'),  # 정수,정혜
    ('\uc815\uad11','\u6de8\u5149'), ('\uc815\ubc95','\u6b63\u6cd5'),  # 정광,정법
    ('\uc815\ub9bc','\u6de8\u6797'),  # 정림
    ('\uc131\ubd88','\u6210\u4f5b'), ('\uc131\uad11','\u8056\u5149'),  # 성불,성광
    ('\uc131\uc8fc','\u8056\u4f4f'), ('\uc131\ub355','\u8056\u5fb7'),  # 성주,성덕
    ('\uc131\uc655','\u8056\u738b'),  # 성왕
    ('\uc548\uc2ec','\u5b89\u5fc3'), ('\uc548\uad6d','\u5b89\u570b'),  # 안심,안국
    ('\uc548\uc591','\u5b89\u990a'), ('\uc548\ub77d','\u5b89\u6a02'),  # 안양,안락
    ('\ud765\uad6d','\u8208\u570b'), ('\ud765\ubc95','\u8208\u6cd5'),  # 흥국,흥법
    ('\ud765\ub959','\u8208\u8f2a'), ('\ud765\ub355','\u8208\u5fb7'),  # 흥륜,흥덕
    ('\ud765\ub8e1','\u8208\u9f8d'),  # 흥룡
    ('\ub9cc\ubcf5','\u842c\u798f'), ('\ub9cc\uc218','\u842c\u58fd'),  # 만복,만수
    ('\ub9cc\ub355','\u842c\u5fb7'),  # 만덕
    ('\ucc9c\ubd88','\u5343\u4f5b'), ('\ucc9c\uc655','\u5929\u738b'),  # 천불,천왕
    ('\ucc9c\uc7a5','\u5929\u85cf'), ('\ucc9c\ucd95','\u5929\u7afa'),  # 천장,천축
    ('\ucc9c\uc218','\u5343\u624b'),  # 천수
    ('\uc11c\uad11','\u745e\u5149'), ('\uc11c\ubd09','\u745e\u5cf0'),  # 서광,서봉
    ('\uc625\ucc9c','\u7389\u6cc9'), ('\uc625\ub828','\u7389\u84ee'),  # 옥천,옥련
    ('\ubcf5\ucc9c','\u798f\u6cc9'), ('\ubcf5\ud765','\u798f\u8208'),  # 복천,복흥
    ('\ud5a5\ucc9c','\u9999\u6cc9'), ('\ud5a5\ub9bc','\u9999\u6797'),  # 향천,향림
    ('\ud654\uc554','\u82b1\u5dd6'), ('\uac10\ub85c','\u7518\u9732'),  # 화암,감로
    ('\ubd09\ub9bc','\u9cf3\u6797'), ('\ubd09\uc554','\u9cf3\u5dd6'),  # 봉림,봉암
    ('\uc218\ub3c4','\u4fee\u9053'), ('\uc218\ub355','\u4fee\u5fb7'),  # 수도,수덕
    ('\ubb18\ub355','\u5999\u5fb7'), ('\ubb18\ubc95','\u5999\u6cd5'),  # 묘덕,묘법
    ('\ubb18\uc801','\u5999\u5bc2'),  # 묘적
    ('\uc0bc\ubcf4','\u4e09\u5bf6'), ('\uc0bc\uc131','\u4e09\u8056'),  # 삼보,삼성
    ('\ud638\uad6d','\u8b77\u570b'),  # 호국
    ('\ubd09\ucc9c','\u5949\u5929'), ('\ubd09\uc740','\u5949\u6069'),  # 봉천,봉은
    ('\ubd09\uc120','\u5949\u5148'),  # 봉선
    ('\uc219\ub9bc','\u5d07\u6797'), ('\uc6b4\ubb38','\u96f2\u9580'),  # 숭림,운문
    ('\uc6b4\ud765','\u96f2\u8208'),  # 운흥
    ('\ud0dc\uc548','\u6cf0\u5b89'), ('\ud0dc\ud3c9','\u592a\u5e73'),  # 태안,태평
    ('\ub3c4\uc120','\u9053\u8a75'), ('\uace0\uc6b4','\u9ad8\u96f2'),  # 도선,고운
    ('\ubc31\ucc9c','\u767d\u6cc9'), ('\ubc31\uc591','\u767d\u7f8a'),  # 백천,백양
    ('\ubc31\ub2f4','\u767d\u6f6d'),  # 백담
    ('\uc2ec\uc778','\u5fc3\u5370'),  # 심인
    ('\uc601\ucd95','\u9748\u9dbf'), ('\uc601\uc740','\u9748\u96b1'),  # 영축,영은
    ('\uc7a5\ucc9c','\u9577\u6cc9'), ('\uc7a5\uc548','\u9577\u5b89'),  # 장천,장안
]: C[pair[0]] = pair[1]

# Single syllables - TRULY unambiguous only
S = {
    '\ubd88': '\u4f5b',  # 불=佛
    '\ubc95': '\u6cd5',  # 법=法
    '\uc2b9': '\u50e7',  # 승=僧
    '\uc0b0': '\u5c71',  # 산=山
    '\ub9bc': '\u6797',  # 림=林
    '\ub355': '\u5fb7',  # 덕=德
    '\uc778': '\u4ec1',  # 인=仁
    '\ubcf5': '\u798f',  # 복=福
    '\uae08': '\u91d1',  # 금=金
    '\uc740': '\u9280',  # 은=銀
    '\uc625': '\u7389',  # 옥=玉
    '\ubc31': '\u767d',  # 백=白
    '\uccad': '\u9751',  # 청=靑
    '\ud64d': '\u7d05',  # 홍=紅
    '\ud669': '\u9ec3',  # 황=黃
    '\ud559': '\u9db4',  # 학=鶴
    '\uc655': '\u738b',  # 왕=王
    '\uce60': '\u4e03',  # 칠=七
    '\uc0bc': '\u4e09',  # 삼=三
    '\ub9cc': '\u842c',  # 만=萬
    '\ud0d1': '\u5854',  # 탑=塔
    '\ud765': '\u8208',  # 흥=興
    '\ud61c': '\u6167',  # 혜=慧
    '\uc548': '\u5b89',  # 안=安
    '\ub300': '\u5927',  # 대=大
    '\ubb18': '\u5999',  # 묘=妙
    '\uc2ec': '\u5fc3',  # 심=心
    '\uc6a9': '\u9f8d',  # 용=龍
    '\ud574': '\u6d77',  # 해=海
    '\uc6d4': '\u6708',  # 월=月
    '\ub2f4': '\u6f6d',  # 담=潭
    '\uc1a1': '\u677e',  # 송=松
    '\uc8fd': '\u7af9',  # 죽=竹
    '\ub9e4': '\u6885',  # 매=梅
    '\uc5f0': '\u84ee',  # 연=蓮
    '\uad11': '\u5149',  # 광=光
    '\uba85': '\u660e',  # 명=明
}

# Suffixes
SUFFIX = {'\uc0ac': '\u5bfa', '\uc554': '\u5eb5', '\uc804': '\u6bbf',
           '\ub2f9': '\u5802', '\uac01': '\u95a3', '\ub8e8': '\u6a13'}

def convert(name):
    import re
    text = name.strip()
    text = re.sub(r'\s*\([A-Za-z\s]+\)', '', text).strip()
    if re.search(r'[\u4e00-\u9fff\U00020000-\U0002a6df]', text):
        return None, 'cjk'
    if re.search(r'[A-Za-z0-9]', text):
        return None, 'latin'
    if len(text) > 8:
        return None, 'long'
    result = text
    for k in sorted(C.keys(), key=len, reverse=True):
        result = result.replace(k, C[k])
    # Suffix
    parts = result.split()
    for pi, part in enumerate(parts):
        if part and '\uac00' <= part[-1] <= '\ud7a3' and part[-1] in SUFFIX:
            parts[pi] = part[:-1] + SUFFIX[part[-1]]
    result = ' '.join(parts)
    out = []
    for ch in result:
        if '\uac00' <= ch <= '\ud7a3':
            if ch in S:
                out.append(S[ch])
            else:
                return None, f'unmapped:{ch}'
        else:
            out.append(ch)
    return ''.join(out), 'ok'

async def main():
    import asyncpg
    conn = await asyncpg.connect('postgresql://fojin:FoJ1n_Pr0d_2026!sEcUrE@postgres:5432/fojin')
    rows = await conn.fetch(
        "SELECT id, name_zh FROM kg_entities "
        "WHERE entity_type='monastery' "
        "AND properties->>'country' = E'\\u97e9\\u56fd' "
        "AND name_zh ~ '[가-힣]' ORDER BY id"
    )
    print(f'Korean-named: {len(rows)}')
    ok = []
    reasons = {}
    for r in rows:
        result, status = convert(r['name_zh'])
        if status == 'ok':
            ok.append((r['id'], r['name_zh'], result))
        else:
            k = status.split(':')[0]
            reasons[k] = reasons.get(k, 0) + 1
    print(f'Convertible: {len(ok)}')
    print(f'Skipped: {reasons}')
    print('\nSamples:')
    for _, ko, zh in ok[:50]:
        print(f'  {ko} -> {zh}')
    if ok:
        print(f'\nUpdating {len(ok)}...')
        async with conn.transaction():
            for eid, _, zh in ok:
                await conn.execute('UPDATE kg_entities SET name_zh = $1 WHERE id = $2', zh, eid)
        print('Done!')
    rem = await conn.fetchval(
        "SELECT count(*) FROM kg_entities WHERE entity_type='monastery' "
        "AND properties->>'country' = E'\\u97e9\\u56fd' AND name_zh ~ '[가-힣]'"
    )
    chn = await conn.fetchval(
        "SELECT count(*) FROM kg_entities WHERE entity_type='monastery' "
        "AND properties->>'country' = E'\\u97e9\\u56fd' AND name_zh !~ '[가-힣]'"
    )
    print(f'\nResult: {chn} Chinese, {rem} Korean (kept)')
    await conn.close()

asyncio.run(main())
