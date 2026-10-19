-- 百度主动推送的推送顺序：近 90 天各内容页的真人访问次数（Umami）。
--
-- 每天只有 10 条推送额度（2026-10-19 百度 remain 字段），推哪些页决定了收录
-- 评估有没有意义，所以按真实访问量从高到低推，而不是按经文编号顺推。
--
-- 在宿主机上跑（Umami 库与 fojin 库在同一个 postgres 实例，umami 用户本地免密）：
--   docker exec -i fojin-postgres psql -U umami -d umami -At -F '	' -v ON_ERROR_STOP=1 \
--     < backend/scripts/baidu_priority.sql > data/baidu-push/priority.tsv
-- 输出：原始 url_path <TAB> 访问次数。归一化（/texts/12/read → /texts/12、
-- 中文词条编码）、合并、校验页面是否存在，都交给 baidu_push.py --priority-file。
--
-- 口径与 2026-10 流量分析一致：只算 fojin 站点（同实例还托管别的站）；剔除
-- 会执行 JS 的爬虫（headless 默认分辨率）；剔除站长本人（访问过 /admin 的会话）；
-- 访问次数 = 不同 visit_id 数，避免一个人刷新多次被放大。
SELECT e.url_path, count(DISTINCT e.visit_id) AS visits
FROM website_event e
JOIN session s USING (session_id)
WHERE e.website_id = 'c757a04c-82e0-4f53-a720-830b0e1a7287'
  AND e.event_type = 1
  AND e.created_at > now() - interval '90 days'
  AND e.url_path ~ '^/(texts|dict|persons)/'
  AND s.screen NOT IN ('800x600', '1024x1024', '1600x1200')
  AND e.session_id NOT IN (
      SELECT DISTINCT session_id
      FROM website_event
      WHERE website_id = 'c757a04c-82e0-4f53-a720-830b0e1a7287' AND url_path LIKE '/admin%'
  )
GROUP BY e.url_path
ORDER BY visits DESC, e.url_path;
