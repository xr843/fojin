import type { JuanAlignmentResponse } from "../../api/client";
import type { AlignmentMap } from "./types";

/**
 * Build a lookup table mapping (fromTextId, fromChunkIndex, toTextId) → toChunkIndex.
 *
 * Null entries are skipped (allows graceful degradation when a per-column alignment
 * fetch failed). Multiple parallels for the same (chunk, toText) keep the first.
 */
export function buildAlignmentMap(
  alignments: Array<JuanAlignmentResponse | null>,
): AlignmentMap {
  const map: AlignmentMap = {};
  for (const a of alignments) {
    if (!a) continue;
    const fromId = a.text_id;
    map[fromId] ??= {};
    for (const entry of a.entries) {
      map[fromId][entry.chunk_index] ??= {};
      for (const p of entry.parallels) {
        if (map[fromId][entry.chunk_index][p.text_id] === undefined) {
          map[fromId][entry.chunk_index][p.text_id] = p.chunk_index;
        }
      }
    }
  }
  return map;
}
