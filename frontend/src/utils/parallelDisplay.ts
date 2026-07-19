import type { ParallelPair } from "../api/client";

/**
 * Whether an aligned parallel carries a real, displayable confidence score.
 *
 * MITRA inline parallels (`source === "mitra-parallel"`) store a constant 1.0
 * as their `confidence` — a mere "import flag" meaning the row passed the
 * import substring gate, NOT a measured quality score (see the backend
 * `alignment_read_model.ParallelRecord.confidence_kind` docstring). Rendering
 * that 1.0 as "置信度 100%" fabricates a confidence the platform never
 * computed. Only fojin (`alignment_pairs`) parallels carry a real
 * LLM/reviewer score, so only they may display a percentage.
 */
export function hasDisplayConfidence(p: Pick<ParallelPair, "source">): boolean {
  return p.source !== "mitra-parallel";
}
