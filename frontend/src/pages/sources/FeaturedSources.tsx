import { useTranslation } from "react-i18next";
import type { DataSource } from "../../api/client";
import { localizedSourceName } from "../../utils/sourceName";
import { FEATURED_SOURCE_CODES, trackSourceClick } from "./constants";

export default function FeaturedSources({ sources }: { sources: DataSource[] }) {
  const { t } = useTranslation();
  const byCode = new Map(sources.map((s) => [s.code, s]));
  // 停用或改名的源静默跳过——名单是常量，目录是数据，两者会漂移。
  const items = FEATURED_SOURCE_CODES.map((c) => byCode.get(c)).filter(
    (s): s is DataSource => !!s && !!s.base_url,
  );
  if (items.length === 0) return null;

  return (
    <section className="sources-featured" aria-labelledby="sources-featured-title">
      <div className="sources-featured-head">
        <h2 id="sources-featured-title" className="sources-featured-title">
          {t("sources.featured_title")}
        </h2>
        <span className="sources-featured-note">{t("sources.featured_note")}</span>
      </div>
      <ul className="sources-featured-list">
        {items.map((s) => (
          <li key={s.code}>
            <a
              href={s.base_url!}
              target="_blank"
              rel="noopener noreferrer"
              className="sources-featured-link"
              title={s.description ?? undefined}
              onClick={() => trackSourceClick(s.code, "visit", { featured: 1 })}
              onAuxClick={(e) => {
                if (e.button === 1) trackSourceClick(s.code, "visit", { featured: 1 });
              }}
            >
              <span className="sources-featured-name">{localizedSourceName(s)}</span>
              {s.description && <span className="sources-featured-desc">{s.description}</span>}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
