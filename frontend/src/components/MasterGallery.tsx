import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Spin, Tooltip } from "antd";
import { getMasters, type MasterProfile } from "../api/client";
import "../styles/master-gallery.css";

/**
 * 祖师长廊 — the master picker.
 *
 * Deliberately has NO portraits. Fabricating faces for real historical teachers
 * would contradict the one thing this product sells (every claim carries a
 * source), so each master is stamped with a cinnabar seal of their name instead
 * — which also happens to be exactly what `--fj-accent: #8b2500` already is.
 *
 * The card's last line is the point: a master's representative line is shown
 * only when it was verified verbatim against that master's own work in our
 * corpus, and it links to the passage. Masters whose writing we don't host say
 * so. The gallery is an extension of the citation discipline, not an exception.
 */

/** Traditions, derived from the `tradition` string the API already returns. */
type Lineage = "india" | "han" | "tibetan" | "theravada";

const LINEAGE_KEYS: Record<Lineage, string> = {
  india: "chat.tradition_india",
  han: "chat.tradition_han",
  tibetan: "chat.tradition_tibetan",
  theravada: "chat.tradition_theravada",
};

function lineageOf(m: MasterProfile): Lineage {
  // Matching against the API's `tradition` data values ("藏传·噶举派", "南传·上座部论师",
  // "印度·中观", …), not UI copy — the displayed chip labels go through t() below.
  const t = m.tradition;
  if (t.startsWith("藏传")) return "tibetan"; // i18n-exempt
  if (t.startsWith("南传")) return "theravada"; // i18n-exempt
  if (t.startsWith("印度")) return "india"; // i18n-exempt
  return "han";
}

/** Seal text: the first two characters of the name — 慧能大师 → 慧能. */
function sealOf(m: MasterProfile): string {
  return Array.from(m.name_zh).slice(0, 2).join("");
}

export function MasterSeal({ text, size = 46 }: { text: string; size?: number }) {
  return (
    <span
      className="mg-seal"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.32) }}
      aria-hidden="true"
    >
      <span className="mg-seal-text">{text}</span>
    </span>
  );
}

/**
 * The strip that stands in for the gallery on the chat's empty state.
 *
 * The full gallery is ~960px tall — taller than the viewport — so putting it
 * inline turned /chat's front page into a wall of cards you had to scroll past
 * before you could do the one thing the page is for: ask a question. But hiding
 * it entirely behind a button is how the 15 personas got lost in the first place.
 *
 * So: the seals stay on the page (they are the thing that makes someone curious —
 * fifteen cinnabar stamps are hard to ignore), and the depth — quotes, 经号,
 * verification badges — lives one click away in the modal.
 */
export function MasterSealStrip({
  selectedId,
  onSelect,
  onOpenAll,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onOpenAll: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { data: masters } = useQuery({
    queryKey: ["chat-masters"],
    queryFn: getMasters,
    staleTime: 60 * 60 * 1000,
  });
  const isEn = i18n.language?.startsWith("en");

  if (!masters?.length) return null;

  return (
    <div className="mg-strip">
      <span className="mg-strip-label">
        {t("chat.gallery_strip", { n: masters.length })}
      </span>
      <span className="mg-strip-seals">
        {masters.map((m) => (
          <Tooltip
            key={m.id}
            title={`${isEn ? m.name_en : m.name_zh} · ${m.tradition}`}
          >
            <button
              type="button"
              className={`mg-strip-seal${selectedId === m.id ? " is-selected" : ""}`}
              aria-pressed={selectedId === m.id}
              aria-label={isEn ? m.name_en : m.name_zh}
              onClick={() => onSelect(m.id)}
            >
              <MasterSeal text={sealOf(m)} size={30} />
            </button>
          </Tooltip>
        ))}
      </span>
      <button type="button" className="mg-strip-all" onClick={onOpenAll}>
        {t("chat.gallery_view_all")} →
      </button>
    </div>
  );
}

interface Props {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Reader deep-link for an epigraph's source passage. */
  onOpenSource?: (textId: number, juan: number) => void;
}

export default function MasterGallery({ selectedId, onSelect, onOpenSource }: Props) {
  const { t, i18n } = useTranslation();
  const [lineage, setLineage] = useState<Lineage | "all">("all");

  const { data: masters, isLoading } = useQuery({
    queryKey: ["chat-masters"],
    queryFn: getMasters,
    staleTime: 60 * 60 * 1000, // curated data; effectively static
  });

  const isEn = i18n.language?.startsWith("en");

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: masters?.length ?? 0 };
    for (const m of masters ?? []) {
      const l = lineageOf(m);
      c[l] = (c[l] ?? 0) + 1;
    }
    return c;
  }, [masters]);

  const shown = useMemo(
    () => (masters ?? []).filter((m) => lineage === "all" || lineageOf(m) === lineage),
    [masters, lineage],
  );

  if (isLoading) {
    return (
      <div className="mg-loading">
        <Spin />
      </div>
    );
  }

  const filters: Array<Lineage | "all"> = ["all", "india", "han", "tibetan", "theravada"];

  return (
    <div className="mg">
      <div className="mg-chips" role="group" aria-label={t("chat.gallery_title")}>
        {filters.map((f) => (
          <button
            key={f}
            type="button"
            className="mg-chip"
            aria-pressed={lineage === f}
            onClick={() => setLineage(f)}
          >
            {f === "all" ? t("chat.tradition_all") : t(LINEAGE_KEYS[f])}
            <span className="mg-chip-n">{counts[f] ?? 0}</span>
          </button>
        ))}
        <button
          type="button"
          className="mg-chip mg-chip-plain"
          aria-pressed={selectedId === null}
          onClick={() => onSelect(null)}
        >
          {t("chat.general_assistant")}
        </button>
      </div>

      <div className="mg-grid">
        {shown.map((m) => {
          const ep = m.epigraph;
          const selected = selectedId === m.id;
          return (
            <button
              key={m.id}
              type="button"
              className={`mg-card${selected ? " is-selected" : ""}`}
              aria-pressed={selected}
              onClick={() => onSelect(m.id)}
            >
              <span className="mg-card-top">
                <MasterSeal text={sealOf(m)} />
                <span className="mg-id">
                  <span className="mg-name">{isEn ? m.name_en : m.name_zh}</span>
                  <span className="mg-meta">
                    <span className="mg-school">{m.tradition}</span> · {m.dates}
                  </span>
                </span>
              </span>

              <span className="mg-rule" />

              {ep ? (
                <>
                  <span className="mg-quote">「{ep.quote}」</span>
                  <span className="mg-src">
                    <span className="mg-ref">
                      {ep.cbeta_id}《{ep.title_zh}》
                    </span>
                    <span className="mg-badge">✓ {t("chat.epigraph_verified")}</span>
                    {onOpenSource && (
                      <span
                        className="mg-open"
                        role="link"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenSource(ep.text_id, ep.juan);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            onOpenSource(ep.text_id, ep.juan);
                          }
                        }}
                      >
                        ↗
                      </span>
                    )}
                  </span>
                </>
              ) : (
                /* No verified line for this master — our corpus holds none of his
                   own writing. That is a reason to show no QUOTE; it was never a
                   reason to show an empty card. The editorial description says what
                   this lineage is about, which is what someone picking one actually
                   needs. Deliberately no quote marks, no citation and no badge: the
                   card makes no claim to be quoting him, so it cannot be wrong about
                   one. Half a gallery of "not set" placeholders reads as unfinished,
                   not as principled. */
                <span className="mg-desc">{m.description}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
