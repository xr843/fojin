import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getTextIdentifiers } from "../api/client";

/** 文本来自哪个数据源 —— 署名 + 回链。
 *
 * 这些数据（`text_identifiers.source_url`）一直存在库里、API 也返回，但在
 * 2026-08-15 之前前端从未调用过 —— 读者只看得到一个藏经名徽章（大正藏 /
 * 甘珠尔 / 巴利三藏），那是**藏经**，不是**数据源**。
 *
 * 为什么补它是义务而非锦上添花：CBETA 用 CC BY-NC-SA，署名是许可条件；
 * 84000 的条款更明确 —— 只写译者或译经团体而不写「84000」本身，不满足其署名
 * 要求。反倒是 SuttaCentral（CC0）根本不要求署名，我们照样署，作为礼节。
 *
 * 失败静默：署名取不到不该把整个文本页拖垮，所以查询失败时什么都不渲染。
 */
export default function SourceAttribution({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["text-identifiers", textId],
    queryFn: () => getTextIdentifiers(textId),
    staleTime: 60 * 60 * 1000, // 来源不会变，缓存一小时
    retry: false,
  });

  if (!data?.length) return null;

  return (
    <div className="source-attribution">
      <span className="source-attribution-label">{t("text.source_label")}</span>
      {data.map((id, i) => (
        <span key={id.id}>
          {i > 0 && <span className="source-attribution-sep">·</span>}
          {id.source_url ? (
            <a href={id.source_url} target="_blank" rel="noopener noreferrer">
              {id.source_name}
            </a>
          ) : (
            <span>{id.source_name}</span>
          )}
        </span>
      ))}
    </div>
  );
}
