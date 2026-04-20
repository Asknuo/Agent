/**
 * 消息搜索引擎 — 支持关键词匹配、角色筛选、时间范围筛选、元数据筛选
 */

import { useState, useEffect, useRef, useCallback } from 'react';

// ── Types ────────────────────────────────────────────

export interface SearchableMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface SearchFilters {
  keyword: string;
  role?: 'user' | 'assistant' | 'all';
  dateRange?: [number, number]; // [startTimestamp, endTimestamp]
  hasMetadata?: boolean;
}

export interface SearchResult {
  messageId: string;
  matchPositions: [number, number][]; // [start, end] highlight positions
}

// ── Core Search Function ─────────────────────────────

export function searchMessages(
  messages: SearchableMessage[],
  filters: SearchFilters,
): SearchResult[] {
  const results: SearchResult[] = [];
  const keyword = filters.keyword.toLowerCase().trim();

  for (const msg of messages) {
    // Role filter
    if (filters.role && filters.role !== 'all' && msg.role !== filters.role) {
      continue;
    }

    // Date range filter
    if (filters.dateRange) {
      const [start, end] = filters.dateRange;
      if (msg.timestamp < start || msg.timestamp > end) {
        continue;
      }
    }

    // Metadata filter
    if (filters.hasMetadata && !msg.metadata) {
      continue;
    }

    // Keyword matching
    if (keyword) {
      const content = msg.content.toLowerCase();
      const positions: [number, number][] = [];
      let searchFrom = 0;

      while (searchFrom < content.length) {
        const idx = content.indexOf(keyword, searchFrom);
        if (idx === -1) break;
        positions.push([idx, idx + keyword.length]);
        searchFrom = idx + 1;
      }

      if (positions.length === 0) continue;
      results.push({ messageId: msg.id, matchPositions: positions });
    } else {
      // No keyword — pass through if other filters matched
      results.push({ messageId: msg.id, matchPositions: [] });
    }
  }

  return results;
}

// ── useMessageSearch Hook (300ms debounce) ───────────

export function useMessageSearch(messages: SearchableMessage[]) {
  const [filters, setFiltersState] = useState<SearchFilters>({ keyword: '' });
  const [results, setResults] = useState<SearchResult[]>([]);
  const [filteredMessages, setFilteredMessages] = useState<SearchableMessage[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setFilters = useCallback((partial: Partial<SearchFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...partial }));
  }, []);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    const hasActiveFilter =
      filters.keyword.trim() !== '' ||
      (filters.role !== undefined && filters.role !== 'all') ||
      filters.dateRange !== undefined ||
      filters.hasMetadata === true;

    if (!hasActiveFilter) {
      setIsSearching(false);
      setResults([]);
      setFilteredMessages(messages);
      return;
    }

    setIsSearching(true);

    debounceRef.current = setTimeout(() => {
      const searchResults = searchMessages(messages, filters);
      setResults(searchResults);

      const matchedIds = new Set(searchResults.map((r) => r.messageId));
      setFilteredMessages(messages.filter((m) => matchedIds.has(m.id)));
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [messages, filters]);

  return { filters, setFilters, results, filteredMessages, isSearching };
}
