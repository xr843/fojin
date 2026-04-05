# Buddhist Geography Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `/map` to viewport-driven geo loading without breaking the current page structure, time slider, lineage toggle, popup flow, or network view.

**Architecture:** Extract viewport/query-param logic into a small testable helper, emit bounds from `DeckGLMap`, and drive `/api/kg/geo` from debounced bounds plus the current map filters in `KGMapPage`. Keep the backend geo API contract unchanged and add regression tests around bounded geo parsing.

**Tech Stack:** React 18 + TanStack Query + Deck.GL + react-map-gl/maplibre + Vitest (frontend), FastAPI + pytest (backend)

---

## File Structure

```
frontend/
  src/api/client.ts                           # MODIFY — export reusable KG geo query param type
  src/components/kg-map/geoQuery.ts          # CREATE — viewport bounds + geo query helpers
  src/components/kg-map/geoQuery.test.ts     # CREATE — unit tests for geo query helper
  src/components/kg-map/DeckGLMap.tsx        # MODIFY — emit initial/move-end bounds to parent
  src/pages/KGMapPage.tsx                    # MODIFY — query geo data from debounced viewport bounds
  src/pages/KGMapPage.test.tsx               # CREATE — integration test for viewport-driven geo fetches
  src/styles/kg-map.css                      # MODIFY — small status-copy styling for viewport updates

backend/
  tests/test_kg.py                           # MODIFY — regression coverage for bounded `/api/kg/geo`
```

---

### Task 1: Shared Geo Query Helper

**Files:**
- Create: `frontend/src/components/kg-map/geoQuery.ts`
- Create: `frontend/src/components/kg-map/geoQuery.test.ts`

- [ ] **Step 1: Write the failing helper tests**

```ts
// frontend/src/components/kg-map/geoQuery.test.ts
import { describe, expect, it } from "vitest";
import {
  buildKGGeoParams,
  DEFAULT_GEO_QUERY_LIMIT,
  DEFAULT_KG_MAP_BOUNDS,
  normalizeBounds,
  sameBounds,
} from "./geoQuery";

describe("normalizeBounds", () => {
  it("rounds viewport bounds to 3 decimal places for stable query keys", () => {
    expect(
      normalizeBounds({
        south: 20.12345,
        west: 100.67891,
        north: 40.98765,
        east: 120.54321,
      }),
    ).toEqual({
      south: 20.123,
      west: 100.679,
      north: 40.988,
      east: 120.543,
    });
  });
});

describe("sameBounds", () => {
  it("treats tiny floating point drift as the same viewport", () => {
    expect(
      sameBounds(DEFAULT_KG_MAP_BOUNDS, {
        south: DEFAULT_KG_MAP_BOUNDS.south + 0.0001,
        west: DEFAULT_KG_MAP_BOUNDS.west - 0.0001,
        north: DEFAULT_KG_MAP_BOUNDS.north + 0.0001,
        east: DEFAULT_KG_MAP_BOUNDS.east - 0.0001,
      }),
    ).toBe(true);
  });
});

describe("buildKGGeoParams", () => {
  it("includes normalized bounds, selected entity types, and the current year", () => {
    expect(
      buildKGGeoParams({
        bounds: {
          south: 20.12345,
          west: 100.67891,
          north: 40.98765,
          east: 120.54321,
        },
        entityTypes: ["monastery", "person"],
        currentYear: 650,
      }),
    ).toEqual({
      south: 20.123,
      west: 100.679,
      north: 40.988,
      east: 120.543,
      entity_type: "monastery,person",
      year_start: 650,
      year_end: 650,
      limit: DEFAULT_GEO_QUERY_LIMIT,
    });
  });

  it("omits year filters when the time slider is disabled", () => {
    expect(
      buildKGGeoParams({
        bounds: DEFAULT_KG_MAP_BOUNDS,
        entityTypes: ["monastery", "place", "person"],
        currentYear: null,
      }),
    ).toEqual({
      south: DEFAULT_KG_MAP_BOUNDS.south,
      west: DEFAULT_KG_MAP_BOUNDS.west,
      north: DEFAULT_KG_MAP_BOUNDS.north,
      east: DEFAULT_KG_MAP_BOUNDS.east,
      entity_type: "monastery,place,person",
      limit: DEFAULT_GEO_QUERY_LIMIT,
    });
  });
});
```

- [ ] **Step 2: Run the helper tests and verify they fail**

Run: `cd /home/lqsxi/projects/fojin/frontend && npm test -- src/components/kg-map/geoQuery.test.ts`

Expected: FAIL with a module resolution error because `src/components/kg-map/geoQuery.ts` does not exist yet.

- [ ] **Step 3: Write the minimal helper implementation**

```ts
// frontend/src/components/kg-map/geoQuery.ts
import type { KGGeoQueryParams } from "../../api/client";

export interface KGMapBounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

export const DEFAULT_GEO_QUERY_LIMIT = 2500;

export const INITIAL_KG_MAP_VIEW_STATE = {
  longitude: 115,
  latitude: 35,
  zoom: 4.2,
  pitch: 0,
  bearing: 0,
} as const;

// Approximation of the initial East Asia-centered camera.
export const DEFAULT_KG_MAP_BOUNDS: KGMapBounds = {
  south: 8,
  west: 72,
  north: 56,
  east: 146,
};

function roundCoord(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export function normalizeBounds(bounds: KGMapBounds): KGMapBounds {
  return {
    south: roundCoord(bounds.south),
    west: roundCoord(bounds.west),
    north: roundCoord(bounds.north),
    east: roundCoord(bounds.east),
  };
}

export function sameBounds(left: KGMapBounds, right: KGMapBounds): boolean {
  const a = normalizeBounds(left);
  const b = normalizeBounds(right);
  return (
    a.south === b.south &&
    a.west === b.west &&
    a.north === b.north &&
    a.east === b.east
  );
}

interface BuildKGGeoParamsOptions {
  bounds: KGMapBounds;
  entityTypes: string[];
  currentYear: number | null;
  limit?: number;
}

export function buildKGGeoParams({
  bounds,
  entityTypes,
  currentYear,
  limit = DEFAULT_GEO_QUERY_LIMIT,
}: BuildKGGeoParamsOptions): KGGeoQueryParams {
  const normalizedBounds = normalizeBounds(bounds);
  const params: KGGeoQueryParams = {
    ...normalizedBounds,
    limit,
  };

  if (entityTypes.length > 0) {
    params.entity_type = entityTypes.join(",");
  }

  if (currentYear !== null) {
    params.year_start = currentYear;
    params.year_end = currentYear;
  }

  return params;
}
```

- [ ] **Step 4: Re-run the helper tests and verify they pass**

Run: `cd /home/lqsxi/projects/fojin/frontend && npm test -- src/components/kg-map/geoQuery.test.ts`

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit the helper + tests**

```bash
git add frontend/src/components/kg-map/geoQuery.ts frontend/src/components/kg-map/geoQuery.test.ts
git commit -m "feat(kg-map): add viewport geo query helpers"
```

---

### Task 2: Viewport-Driven KG Map Querying

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/kg-map/DeckGLMap.tsx`
- Modify: `frontend/src/pages/KGMapPage.tsx`
- Modify: `frontend/src/styles/kg-map.css`
- Create: `frontend/src/pages/KGMapPage.test.tsx`

- [ ] **Step 1: Write the failing page integration tests**

```tsx
// frontend/src/pages/KGMapPage.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getKGGeoEntities, getKGLineageArcs } from "../api/client";
import {
  DEFAULT_GEO_QUERY_LIMIT,
  DEFAULT_KG_MAP_BOUNDS,
  type KGMapBounds,
} from "../components/kg-map/geoQuery";
import KGMapPage from "./KGMapPage";

const NEXT_BOUNDS: KGMapBounds = {
  south: 20,
  west: 90,
  north: 36,
  east: 118,
};

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    getKGGeoEntities: vi.fn(),
    getKGLineageArcs: vi.fn(),
  };
});

vi.mock("../components/kg-map/DeckGLMap", () => ({
  default: ({ onBoundsChange }: { onBoundsChange?: (bounds: KGMapBounds) => void }) => (
    <div>
      <button type="button" onClick={() => onBoundsChange?.(NEXT_BOUNDS)}>
        emit viewport change
      </button>
    </div>
  ),
}));

vi.mock("../components/kg-map/TimeSlider", () => ({
  default: () => <div>time slider</div>,
}));

vi.mock("../components/kg-map/LineageGraph", () => ({
  default: () => <div>lineage graph</div>,
}));

vi.mock("../components/kg-map/MapEntityPopup", () => ({
  default: () => <div>map popup</div>,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <KGMapPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("KGMapPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(getKGGeoEntities).mockResolvedValue({
      entities: [
        {
          id: 1,
          entity_type: "person",
          name_zh: "玄奘",
          name_en: "Xuanzang",
          description: "唐代译经师",
          latitude: 34.2667,
          longitude: 108.9,
          year_start: 602,
          year_end: 664,
        },
      ],
      total: 1,
    });
    vi.mocked(getKGLineageArcs).mockResolvedValue({ arcs: [], total: 0 });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("loads geo entities for the initial viewport instead of requesting 50000 rows", async () => {
    renderPage();

    await waitFor(() => expect(getKGGeoEntities).toHaveBeenCalledTimes(1));

    expect(getKGGeoEntities).toHaveBeenCalledWith({
      south: DEFAULT_KG_MAP_BOUNDS.south,
      west: DEFAULT_KG_MAP_BOUNDS.west,
      north: DEFAULT_KG_MAP_BOUNDS.north,
      east: DEFAULT_KG_MAP_BOUNDS.east,
      entity_type: "monastery,place,person",
      limit: DEFAULT_GEO_QUERY_LIMIT,
    });

    expect(screen.getByText("当前视窗 1 个实体")).toBeInTheDocument();
  });

  it("debounces viewport changes before issuing another geo query", async () => {
    renderPage();

    await waitFor(() => expect(getKGGeoEntities).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "emit viewport change" }));

    act(() => {
      vi.advanceTimersByTime(249);
    });
    expect(getKGGeoEntities).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });

    await waitFor(() => expect(getKGGeoEntities).toHaveBeenCalledTimes(2));

    expect(getKGGeoEntities).toHaveBeenLastCalledWith({
      south: NEXT_BOUNDS.south,
      west: NEXT_BOUNDS.west,
      north: NEXT_BOUNDS.north,
      east: NEXT_BOUNDS.east,
      entity_type: "monastery,place,person",
      limit: DEFAULT_GEO_QUERY_LIMIT,
    });
  });
});
```

- [ ] **Step 2: Run the page tests and verify they fail**

Run: `cd /home/lqsxi/projects/fojin/frontend && npm test -- src/pages/KGMapPage.test.tsx`

Expected: FAIL because `KGMapPage` still calls `getKGGeoEntities({ limit: 50000 })`, does not expose viewport-driven query params, and does not show the new header copy.

- [ ] **Step 3: Implement the minimal viewport-driven querying flow**

```ts
// frontend/src/api/client.ts
export interface KGGeoQueryParams {
  entity_type?: string;
  year_start?: number;
  year_end?: number;
  south?: number;
  west?: number;
  north?: number;
  east?: number;
  limit?: number;
}

export async function getKGGeoEntities(params?: KGGeoQueryParams): Promise<KGGeoResponse> {
  const { data } = await api.get<KGGeoResponse>("/kg/geo", { params });
  return data;
}
```

```tsx
// frontend/src/components/kg-map/DeckGLMap.tsx
import { useState, useMemo, useCallback, useRef } from "react";
import { Map, type MapRef } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { escapeHtml } from "../../utils/sanitize";
import type { KGGeoEntity, KGLineageArc } from "../../api/client";
import {
  INITIAL_KG_MAP_VIEW_STATE,
  type KGMapBounds,
} from "./geoQuery";

interface DeckGLMapProps {
  geoEntities: KGGeoEntity[];
  lineageArcs: KGLineageArc[];
  showArcs: boolean;
  currentYear: number | null;
  entityTypeFilter: string[];
  onEntityClick: (entity: KGGeoEntity) => void;
  onBoundsChange?: (bounds: KGMapBounds) => void;
}

export default function DeckGLMap({
  geoEntities,
  lineageArcs,
  showArcs,
  currentYear,
  entityTypeFilter,
  onEntityClick,
  onBoundsChange,
}: DeckGLMapProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const mapRef = useRef<MapRef>(null);

  const emitBounds = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map || !onBoundsChange) return;
    const bounds = map.getBounds();
    onBoundsChange({
      south: bounds.getSouth(),
      west: bounds.getWest(),
      north: bounds.getNorth(),
      east: bounds.getEast(),
    });
  }, [onBoundsChange]);

  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;

    const layers = map.getStyle().layers || [];
    for (const layer of layers) {
      if (layer.type === "symbol" && layer.layout && "text-field" in layer.layout) {
        try {
          map.setLayoutProperty(layer.id, "text-field", [
            "coalesce",
            ["get", "name:zh"],
            ["get", "name_zh"],
            ["get", "name:zh-Hans"],
            ["get", "name_int"],
            ["get", "name"],
          ]);
        } catch {
          // skip unsupported layers
        }
      }
    }

    emitBounds();
  }, [emitBounds]);

  return (
    <DeckGL
      initialViewState={INITIAL_KG_MAP_VIEW_STATE}
      controller
      layers={layers}
      style={{ position: "absolute", inset: "0" }}
    >
      <Map
        ref={mapRef}
        mapStyle={MAP_STYLE}
        onLoad={handleMapLoad}
        onMoveEnd={emitBounds}
      />
    </DeckGL>
  );
}
```

```tsx
// frontend/src/pages/KGMapPage.tsx
import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Spin, Empty, Tooltip, Radio, Select } from "antd";
import { GlobalOutlined, BarChartOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import DeckGLMap from "../components/kg-map/DeckGLMap";
import MapEntityPopup from "../components/kg-map/MapEntityPopup";
import TimeSlider from "../components/kg-map/TimeSlider";
import LineageGraph from "../components/kg-map/LineageGraph";
import { getKGGeoEntities, getKGLineageArcs } from "../api/client";
import type { KGGeoEntity } from "../api/client";
import {
  buildKGGeoParams,
  DEFAULT_KG_MAP_BOUNDS,
  sameBounds,
  type KGMapBounds,
} from "../components/kg-map/geoQuery";
import "../styles/kg-map.css";

export default function KGMapPage() {
  const navigate = useNavigate();
  const [entityTypes, setEntityTypes] = useState<string[]>(["monastery", "place", "person"]);
  const [showArcs, setShowArcs] = useState(false);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<KGGeoEntity | null>(null);
  const [viewMode, setViewMode] = useState<"map" | "network">("map");
  const [schoolFilter, setSchoolFilter] = useState<string | null>(null);
  const [mapBounds, setMapBounds] = useState<KGMapBounds>(DEFAULT_KG_MAP_BOUNDS);
  const [debouncedBounds, setDebouncedBounds] = useState<KGMapBounds>(DEFAULT_KG_MAP_BOUNDS);

  useEffect(() => {
    if (viewMode === "network" && !showArcs) setShowArcs(true);
  }, [viewMode, showArcs]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedBounds(mapBounds);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [mapBounds]);

  const geoParams = useMemo(
    () =>
      buildKGGeoParams({
        bounds: debouncedBounds,
        entityTypes,
        currentYear,
      }),
    [debouncedBounds, entityTypes, currentYear],
  );

  const { data: geoData, isLoading: geoLoading, isFetching: geoFetching } = useQuery({
    queryKey: ["kg-geo", geoParams],
    queryFn: () => getKGGeoEntities(geoParams),
    staleTime: 5 * 60_000,
    placeholderData: (previousData) => previousData,
    enabled: viewMode === "map",
  });

  const { data: arcData } = useQuery({
    queryKey: ["kg-lineage-arcs"],
    queryFn: () => getKGLineageArcs({ limit: 8000 }),
    staleTime: 5 * 60_000,
    enabled: showArcs,
  });

  const handleBoundsChange = (nextBounds: KGMapBounds) => {
    setMapBounds((previousBounds) =>
      sameBounds(previousBounds, nextBounds) ? previousBounds : nextBounds,
    );
  };

  return (
    <div className="kg-map-page">
      <div className="kg-map-header">
        <GlobalOutlined />
        <h3>佛教地理</h3>
        {geoData && (
          <Tooltip title="当前地图视窗中符合筛选条件的实体数量">
            <span className="kg-map-stats">
              <BarChartOutlined />
              <span>{`当前视窗 ${geoData.total.toLocaleString()} 个实体`}</span>
              {geoFetching && <span className="kg-map-stats-hint">地图更新中</span>}
            </span>
          </Tooltip>
        )}
      </div>

      <div className="kg-map-container">
        {geoLoading ? (
          <div className="kg-map-loading">
            <Spin size="large" />
          </div>
        ) : !geoData?.entities.length ? (
          <div className="kg-map-loading">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前视窗暂无地理数据" />
          </div>
        ) : (
          <DeckGLMap
            geoEntities={geoData.entities}
            lineageArcs={arcData?.arcs ?? []}
            showArcs={showArcs}
            currentYear={currentYear}
            entityTypeFilter={entityTypes}
            onEntityClick={handleEntityClick}
            onBoundsChange={handleBoundsChange}
          />
        )}
      </div>
    </div>
  );
}
```

```css
/* frontend/src/styles/kg-map.css */
.kg-map-stats-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--fj-ink-light);
}
```

- [ ] **Step 4: Run the frontend tests and verify they pass**

Run: `cd /home/lqsxi/projects/fojin/frontend && npm test -- src/components/kg-map/geoQuery.test.ts src/pages/KGMapPage.test.tsx`

Expected: PASS with `6 passed`.

- [ ] **Step 5: Run frontend static checks**

Run: `cd /home/lqsxi/projects/fojin/frontend && npx eslint src/api/client.ts src/components/kg-map/geoQuery.ts src/components/kg-map/geoQuery.test.ts src/components/kg-map/DeckGLMap.tsx src/pages/KGMapPage.tsx src/pages/KGMapPage.test.tsx src/styles/kg-map.css`

Expected: no errors

Run: `cd /home/lqsxi/projects/fojin/frontend && npx tsc -b --noEmit`

Expected: success with no TypeScript errors

- [ ] **Step 6: Commit the viewport-driven map changes**

```bash
git add frontend/src/api/client.ts frontend/src/components/kg-map/geoQuery.ts frontend/src/components/kg-map/geoQuery.test.ts frontend/src/components/kg-map/DeckGLMap.tsx frontend/src/pages/KGMapPage.tsx frontend/src/pages/KGMapPage.test.tsx frontend/src/styles/kg-map.css
git commit -m "feat(kg-map): load geo entities by viewport"
```

---

### Task 3: Backend Geo Endpoint Regression Coverage

**Files:**
- Modify: `backend/tests/test_kg.py`

- [ ] **Step 1: Add bounded-geo regression tests**

```py
# backend/tests/test_kg.py
from unittest.mock import ANY, AsyncMock, MagicMock, patch

GEO_ROWS = [
    {
        "id": 1,
        "entity_type": "person",
        "name_zh": "玄奘",
        "name_en": "Xuanzang",
        "description": "唐代译经师",
        "latitude": 34.2667,
        "longitude": 108.9,
        "year_start": 602,
        "year_end": 664,
    }
]


@pytest.mark.anyio
async def test_geo_endpoint_forwards_bounds_filters_and_limit(kg_client):
    with patch(f"{_KG_API}.get_geo_entities", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = (GEO_ROWS, 1)

        resp = await kg_client.get(
            "/api/kg/geo",
            params={
                "entity_type": "monastery,person",
                "year_start": 650,
                "year_end": 650,
                "south": 20,
                "west": 100,
                "north": 40,
                "east": 120,
                "limit": 2500,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        mock_geo.assert_awaited_once_with(
            ANY,
            ["monastery", "person"],
            650,
            650,
            (20.0, 100.0, 40.0, 120.0),
            2500,
        )


@pytest.mark.anyio
async def test_geo_endpoint_keeps_unbounded_calls_compatible(kg_client):
    with patch(f"{_KG_API}.get_geo_entities", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = (GEO_ROWS, 1)

        resp = await kg_client.get("/api/kg/geo", params={"limit": 5000})

        assert resp.status_code == 200
        assert resp.json()["entities"][0]["name_zh"] == "玄奘"
        mock_geo.assert_awaited_once_with(ANY, None, None, None, None, 5000)
```

- [ ] **Step 2: Run the backend KG tests**

Run: `cd /home/lqsxi/projects/fojin/backend && pytest tests/test_kg.py -q`

Expected: PASS with `8 passed` if the current handler already matches the contract. If this step fails, fix only the request-parsing layer in `backend/app/api/knowledge_graph.py` without changing the response schema.

- [ ] **Step 3: If parsing needs alignment, keep the fix minimal**

```py
# backend/app/api/knowledge_graph.py
entity_types = (
    [t.strip() for t in entity_type.split(",") if t.strip()]
    if entity_type
    else None
)
bounds = None
if all(v is not None for v in (south, west, north, east)):
    bounds = (south, west, north, east)
entities, total = await get_geo_entities(
    db, entity_types, year_start, year_end, bounds, limit
)
```

- [ ] **Step 4: Commit the regression coverage**

```bash
git add backend/tests/test_kg.py backend/app/api/knowledge_graph.py
git commit -m "test(kg): cover bounded geo query contract"
```

---

### Task 4: Final Verification and Manual QA

**Files:**
- Verify only:
  - `frontend/src/api/client.ts`
  - `frontend/src/components/kg-map/geoQuery.ts`
  - `frontend/src/components/kg-map/geoQuery.test.ts`
  - `frontend/src/components/kg-map/DeckGLMap.tsx`
  - `frontend/src/pages/KGMapPage.tsx`
  - `frontend/src/pages/KGMapPage.test.tsx`
  - `frontend/src/styles/kg-map.css`
  - `backend/tests/test_kg.py`
  - `backend/app/api/knowledge_graph.py` (only if touched in Task 3)

- [ ] **Step 1: Re-run focused automated checks**

Run: `cd /home/lqsxi/projects/fojin/frontend && npm test -- src/components/kg-map/geoQuery.test.ts src/pages/KGMapPage.test.tsx`

Expected: PASS with `6 passed`

Run: `cd /home/lqsxi/projects/fojin/frontend && npx eslint src/api/client.ts src/components/kg-map/geoQuery.ts src/components/kg-map/geoQuery.test.ts src/components/kg-map/DeckGLMap.tsx src/pages/KGMapPage.tsx src/pages/KGMapPage.test.tsx src/styles/kg-map.css`

Expected: no errors

Run: `cd /home/lqsxi/projects/fojin/frontend && npx tsc -b --noEmit`

Expected: success

Run: `cd /home/lqsxi/projects/fojin/backend && pytest tests/test_kg.py -q`

Expected: PASS with `8 passed`

- [ ] **Step 2: Start the local stack for manual QA**

Run: `cd /home/lqsxi/projects/fojin && docker compose up -d postgres redis elasticsearch backend frontend`

Expected: the FoJin containers start and the frontend becomes reachable at the local frontend URL configured by the compose stack.

- [ ] **Step 3: Execute the manual QA checklist**

1. Open `/map`
2. Confirm the page shows entities on first load without waiting for a full 50,000-row request
3. Pan the map and confirm results refresh after a short debounce
4. Zoom the map and confirm results refresh after a short debounce
5. Toggle entity types and confirm geo results update
6. Enable the time filter and confirm geo results update
7. Enable lineage arcs and confirm the overlay still appears
8. Switch to network view and confirm it still renders
9. Switch back to map view and confirm the map still works
10. Click an entity and confirm the popup still opens

- [ ] **Step 4: Record any regressions before merging**

If any check fails, fix that regression before additional scope. Do not begin popup redesign, new detail flows, or clustering in this phase.
