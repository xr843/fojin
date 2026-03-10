const SEARCH_KEY = "fojin-search-history";
const VIEW_KEY = "fojin-view-history";
const MAX_SEARCH = 50;
const MAX_VIEW = 100;

export interface SearchHistoryItem {
  query: string;
  tab: string;
  timestamp: number;
}

export interface ViewHistoryItem {
  textId: number;
  title: string;
  path: string;
  timestamp: number;
}

function load<T>(key: string): T[] {
  try {
    return JSON.parse(localStorage.getItem(key) || "[]");
  } catch {
    return [];
  }
}

export function getSearchHistory(): SearchHistoryItem[] {
  return load<SearchHistoryItem>(SEARCH_KEY);
}

export function addSearchHistory(query: string, tab = "catalog") {
  if (!query.trim()) return;
  const items = getSearchHistory().filter((h) => h.query !== query);
  items.unshift({ query, tab, timestamp: Date.now() });
  localStorage.setItem(SEARCH_KEY, JSON.stringify(items.slice(0, MAX_SEARCH)));
}

export function getViewHistory(): ViewHistoryItem[] {
  return load<ViewHistoryItem>(VIEW_KEY);
}

export function addViewHistory(textId: number, title: string, path: string) {
  const items = getViewHistory().filter((h) => h.textId !== textId);
  items.unshift({ textId, title, path, timestamp: Date.now() });
  localStorage.setItem(VIEW_KEY, JSON.stringify(items.slice(0, MAX_VIEW)));
}

export function clearSearchHistory() {
  localStorage.removeItem(SEARCH_KEY);
}

export function clearViewHistory() {
  localStorage.removeItem(VIEW_KEY);
}
