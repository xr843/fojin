import { create } from "zustand";
import type { TimelineDimension } from "../api/stats";

interface TimelineState {
  dimension: TimelineDimension;
  setDimension: (d: TimelineDimension) => void;
  scholarlyMode: boolean;
  toggleScholarlyMode: () => void;
  filters: {
    category: string | null;
    language: string | null;
    sourceId: string | null;
  };
  setFilter: (key: "category" | "language" | "sourceId", value: string | null) => void;
  resetFilters: () => void;
}

export const useTimelineStore = create<TimelineState>()((set) => ({
  dimension: "texts",
  setDimension: (dimension) => set({ dimension }),
  scholarlyMode: false,
  toggleScholarlyMode: () => set((s) => ({ scholarlyMode: !s.scholarlyMode })),
  filters: { category: null, language: null, sourceId: null },
  setFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),
  resetFilters: () =>
    set({ filters: { category: null, language: null, sourceId: null } }),
}));
