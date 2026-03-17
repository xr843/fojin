/**
 * Citation format generators for Buddhist texts.
 *
 * Generates BibTeX, RIS, and APA citation strings from text metadata.
 * Pure frontend — no backend API needed.
 */

export interface CitationMeta {
  id: number;
  cbetaId: string;
  titleZh: string;
  titleEn?: string | null;
  translator?: string | null;
  dynasty?: string | null;
  category?: string | null;
  url?: string;
}

/** Sanitise a string for use as a BibTeX key (ASCII only, no spaces). */
function bibKey(meta: CitationMeta): string {
  return meta.cbetaId.replace(/[^a-zA-Z0-9]/g, "_");
}

/** Build the canonical FoJin URL for a text. */
function canonicalUrl(meta: CitationMeta): string {
  return meta.url ?? `https://fojin.app/texts/${meta.id}`;
}

/** Format author field — uses translator if available, otherwise "CBETA". */
function authorField(meta: CitationMeta): string {
  if (meta.translator) {
    return meta.dynasty ? `${meta.translator} (${meta.dynasty})` : meta.translator;
  }
  return "CBETA";
}

// ---------------------------------------------------------------------------
// BibTeX
// ---------------------------------------------------------------------------

export function toBibTeX(meta: CitationMeta): string {
  const key = bibKey(meta);
  const author = authorField(meta);
  const title = meta.titleEn
    ? `${meta.titleZh} (${meta.titleEn})`
    : meta.titleZh;
  const url = canonicalUrl(meta);

  const lines = [
    `@misc{${key},`,
    `  title   = {${title}},`,
    `  author  = {${author}},`,
    `  note    = {CBETA ${meta.cbetaId}${meta.category ? `, ${meta.category}` : ""}},`,
    `  url     = {${url}},`,
    `  urldate = {${new Date().toISOString().slice(0, 10)}}`,
    `}`,
  ];
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// RIS
// ---------------------------------------------------------------------------

export function toRIS(meta: CitationMeta): string {
  const author = authorField(meta);
  const url = canonicalUrl(meta);

  const lines = [
    "TY  - BOOK",
    `TI  - ${meta.titleZh}`,
    `AU  - ${author}`,
    `ID  - ${meta.cbetaId}`,
  ];
  if (meta.titleEn) lines.push(`T2  - ${meta.titleEn}`);
  if (meta.category) lines.push(`KW  - ${meta.category}`);
  if (meta.dynasty) lines.push(`N1  - ${meta.dynasty}`);
  lines.push(
    `UR  - ${url}`,
    `Y2  - ${new Date().toISOString().slice(0, 10)}`,
    "ER  - ",
  );
  return lines.join("\r\n");
}

// ---------------------------------------------------------------------------
// APA (7th edition style)
// ---------------------------------------------------------------------------

export function toAPA(meta: CitationMeta): string {
  const author = authorField(meta);
  const url = canonicalUrl(meta);
  const accessDate = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  // Author. (Dynasty/n.d.). Title (CBETA ID). Source. URL
  const datePart = meta.dynasty ?? "n.d.";
  const titlePart = meta.titleEn
    ? `${meta.titleZh} [${meta.titleEn}]`
    : meta.titleZh;

  return `${author}. (${datePart}). ${titlePart} (CBETA ${meta.cbetaId}). 佛津 FoJin. ${url} (${accessDate} 访问)`;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export type CitationFormat = "bibtex" | "ris" | "apa";

export function generateCitation(
  format: CitationFormat,
  meta: CitationMeta,
): string {
  switch (format) {
    case "bibtex":
      return toBibTeX(meta);
    case "ris":
      return toRIS(meta);
    case "apa":
      return toAPA(meta);
  }
}

const FILE_EXT: Record<CitationFormat, string> = {
  bibtex: ".bib",
  ris: ".ris",
  apa: ".txt",
};

const MIME_TYPE: Record<CitationFormat, string> = {
  bibtex: "application/x-bibtex",
  ris: "application/x-research-info-systems",
  apa: "text/plain",
};

/** Trigger a file download in the browser. */
export function downloadCitation(
  format: CitationFormat,
  meta: CitationMeta,
): void {
  const text = generateCitation(format, meta);
  const blob = new Blob([text], { type: MIME_TYPE[format] });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${meta.cbetaId}${FILE_EXT[format]}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
