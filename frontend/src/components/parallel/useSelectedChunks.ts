import { useCallback, useState } from "react";
import type { AiDiffChunkInput } from "../../api/client";

export interface UseSelectedChunksReturn {
  selected: AiDiffChunkInput[];
  toggle: (c: AiDiffChunkInput) => void;
  clear: () => void;
}

function sameChunk(a: AiDiffChunkInput, b: AiDiffChunkInput): boolean {
  return a.text_id === b.text_id && a.chunk_index === b.chunk_index;
}

export function useSelectedChunks(): UseSelectedChunksReturn {
  const [selected, setSelected] = useState<AiDiffChunkInput[]>([]);

  const toggle = useCallback((c: AiDiffChunkInput) => {
    setSelected((prev) => {
      const i = prev.findIndex((p) => sameChunk(p, c));
      if (i >= 0) return prev.filter((_, j) => j !== i);
      return [...prev, c];
    });
  }, []);

  const clear = useCallback(() => setSelected([]), []);

  return { selected, toggle, clear };
}
