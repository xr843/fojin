import type { ParallelTextContent, JuanAlignmentResponse } from "../../api/client";

/** A single column's data (text content + its own alignment table). */
export interface ColumnData {
  text: ParallelTextContent;
  /** Alignment data for this column (its chunks + parallels to other columns). May be null when API failed. */
  alignment: JuanAlignmentResponse | null;
}

/**
 * For column A.chunk_index = i, what is the corresponding chunk_index in column B?
 *
 *   map[textA_id]?.[chunk_i]?.[textB_id] === chunk_j_in_B
 *
 * Symmetric: built so both (A→B) and (B→A) entries exist.
 */
export type AlignmentMap = Record<number, Record<number, Record<number, number>>>;
