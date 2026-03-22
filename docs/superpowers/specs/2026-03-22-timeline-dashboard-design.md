# Timeline & Dashboard Design Spec

## Overview

Two new features for FoJin: a multi-dimensional historical timeline and a data statistics dashboard. Both serve researchers and casual learners, with a "scholarly mode" toggle for deeper data.

## Feature 1: Historical Timeline (`/timeline`)

### Core Concept

A horizontal timeline with real year axis (500 BCE - 2000 CE). Dynasties render as colored background bands. Texts, figures, and schools appear as nodes positioned by their dynasty's year range (or exact year when available).

### Dimensions (User-Switchable)

1. **Texts** (default) — Buddhist texts positioned by dynasty/translation period. Click to navigate to text detail.
2. **Figures** — Translators, monks, patriarchs. Positioned by `active_in` dynasty relationship from KG.
3. **Schools/Sects** — Buddhist schools positioned by founding period.

User switches via tab bar above the timeline. Each dimension queries different data.

### Dynasty-Year Mapping

A static config (`dynasty_years.ts`) maps ~30 dynasties to year ranges:

```typescript
interface DynastyPeriod {
  key: string;        // "tang"
  name_zh: string;    // "唐"
  name_en: string;    // "Tang Dynasty"
  start: number;      // 618
  end: number;        // 907
  color: string;      // band color
}
```

Texts with only a dynasty field are distributed within that dynasty's range using a deterministic spread (hash-based positioning to avoid overlap, consistent across renders).

### Visual Design

- **Background**: Dynasty bands as vertical colored strips with dynasty name labels at top
- **Nodes**: Circular dots with hover tooltip (title, dynasty, translator). Size varies by text significance (e.g., number of translations/relations).
- **Zoom**: Scroll to zoom into a dynasty; pinch on mobile. Pan by drag.
- **Scholarly mode toggle**: Shows exact year labels, adds uncertainty indicators (semi-transparent bars for estimated dates), and displays source attribution.
- **Style**: Follow existing FoJin classical aesthetic — warm paper background, ink/cinnabar accents, Noto Serif SC.

### Interactions

- **Hover**: Tooltip with key metadata
- **Click**: Navigate to text detail / KG entity
- **Filter sidebar**: Filter by category (sutra/vinaya/abhidharma/commentary), language, source
- **Search**: Quick search within timeline results

### API

```
GET /api/stats/timeline?dimension=texts|figures|schools
  &category=sutra,vinaya
  &language=zh,sa
  &source_id=1,2
  &page=1&page_size=200

Response: {
  items: [{
    id, name_zh, name_en, dynasty, year_start?, year_end?,
    category?, entity_type?, relation_count?
  }],
  dynasty_distribution: { "tang": 234, "song": 189, ... },
  total: 1200
}
```

Offset-based pagination (`page` + `page_size`). Backend computes `year_start/year_end` from dynasty mapping when not explicitly set. Redis cache: 1 hour TTL.

## Feature 2: Statistics Dashboard (`/dashboard`)

### Layout

Single page with card-based grid layout (responsive: 2 cols desktop, 1 col mobile).

### Charts

1. **Dynasty Distribution** (bar chart) — Text count per dynasty, horizontal bars sorted chronologically. Clickable bars filter other charts.
2. **Language Distribution** (donut chart) — Texts by language, top 10 + "other"
3. **Category Breakdown** (treemap or nested donut) — Sutra/Vinaya/Abhidharma/Commentary hierarchy
4. **Data Source Coverage** (horizontal stacked bar) — Per-source: texts with full content vs metadata-only vs external link
5. **Translation Activity Over Time** (area chart) — Texts per dynasty as a trend line, showing peaks (e.g., Tang dynasty translation boom)
6. **Top Translators** (bar chart) — Top 15 translators by text count
7. **Knowledge Graph Stats** (number cards) — Entity count, relation count, coverage percentage
8. **Platform Summary** (number cards at top) — Total texts, sources, languages, dictionary entries

### Scholarly Mode

Toggles additional detail:
- Exact numbers on all charts (not just hover)
- Percentage labels
- Data source attribution footnotes
- CSV export button per chart

### API

```
GET /api/stats/overview

Response: {
  summary: { total_texts, total_sources, total_languages, total_dict_entries, total_kg_entities, total_kg_relations },
  dynasty_distribution: [{ dynasty, count, year_start, year_end }],
  language_distribution: [{ language, count }],
  category_distribution: [{ category, count, subcategories: [...] }],
  source_coverage: [{ source_name, full_content, metadata_only, external_link }],
  top_translators: [{ name, dynasty, count }]
}
```

Single aggregation query, cached in Redis for 1 hour.

## Technical Design

### Frontend

- **Visualization**: D3.js (already installed). No new chart libraries.
  - Timeline: Custom D3 component with zoom/pan behavior
  - Dashboard charts: D3-based reusable chart components
- **State**: Zustand store for timeline filters + scholarly mode toggle
- **Data fetching**: TanStack Query with `staleTime: 3600000` (1hr, matches backend cache)
- **Routing**: Add `/timeline` and `/dashboard` as lazy-loaded routes in App.tsx
- **Responsive**: Ant Design Grid for dashboard layout; timeline horizontal scroll on mobile

### Backend

- **New router**: `backend/app/api/stats.py` with 2 endpoints
- **Service**: `backend/app/services/stats_service.py` — aggregation queries using SQLAlchemy + raw SQL for complex counts
- **Dynasty mapping**: Shared `backend/app/core/dynasty_config.py` (Python dict, same data as frontend)
- **Cache**: Redis with `stats:overview` and `stats:timeline:{hash}` keys, 1hr TTL
- **No model changes**: All computed from existing `buddhist_texts.dynasty`, `kg_entities`, `kg_relations`
- **Dynasty config sync**: `dynasty_years.ts` (frontend) and `dynasty_config.py` (backend) must stay in sync. Add a test that validates parity by comparing the JSON export of both configs.

### New Files

```
frontend/
  src/pages/TimelinePage.tsx
  src/pages/DashboardPage.tsx
  src/components/timeline/
    TimelineChart.tsx        # Main D3 timeline
    DynastyBands.tsx         # Background dynasty strips
    TimelineFilters.tsx      # Filter sidebar
    TimelineTooltip.tsx      # Hover tooltip
  src/components/dashboard/
    DynastyBarChart.tsx
    LanguageDonut.tsx
    CategoryTreemap.tsx
    SourceCoverageChart.tsx
    TranslationTrendChart.tsx
    TopTranslatorsChart.tsx
    SummaryCards.tsx
  src/data/dynasty_years.ts  # Dynasty-year mapping config
  src/api/stats.ts           # API client functions
  src/stores/timelineStore.ts

backend/
  app/api/stats.py
  app/services/stats_service.py
  app/core/dynasty_config.py
  tests/test_stats.py
```

### Performance

- Backend aggregation queries should complete <500ms (indexed dynasty column + KG entity_type)
- Redis cache eliminates repeated computation
- Frontend lazy loads both pages
- D3 timeline uses SVG rendering (sufficient for typical result sets of ~200 nodes per page)
- Dashboard charts render progressively (summary cards first, then charts)

### Testing

- **Backend**: pytest for stats endpoints (mock DB with known data, verify aggregation correctness)
- **Frontend**: TypeScript strict mode, ESLint. Manual visual QA for chart rendering.

## Data Enhancement Path (Future Iterations)

1. Add `year_start`/`year_end` fields to `KGEntity.properties` JSON for figures with known dates
2. Add `translation_year` to `BuddhistText` model for texts with known dates
3. Import CBETA chronological data where available
4. Gradually replace dynasty-estimated positions with precise years
5. Add geographic dimension (map visualization) as a future feature

## Navigation

- Add "Timeline" and "Dashboard" entries to the main navigation menu
- Timeline icon: clock/history icon
- Dashboard icon: chart/bar-chart icon

## Scope Exclusions

- No map/geographic visualization (future feature)
- No real-time data updates (static aggregation is sufficient)
- No user-customizable dashboard (fixed layout)
- No data editing from timeline/dashboard (read-only views)
