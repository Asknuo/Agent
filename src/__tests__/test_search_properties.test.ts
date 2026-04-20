/**
 * Property-Based Tests for the search engine.
 *
 * Validates:
 * - Correctness Property 5: Search result subset — every result messageId exists in input
 * - Correctness Property 6: Order preservation — results maintain original message order
 * - Correctness Property 7: Empty keyword full match — no filters returns all messages
 * - Correctness Property 8: Highlight position validity — 0 <= start < end <= content.length
 * - Role filter correctness — filtered results only contain matching roles
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { searchMessages, SearchableMessage, SearchFilters } from '../search';

// ── Arbitraries ──────────────────────────────────────

const messageArb: fc.Arbitrary<SearchableMessage> = fc.record({
  id: fc.uuid(),
  role: fc.constantFrom('user' as const, 'assistant' as const),
  content: fc.string({ minLength: 0, maxLength: 200 }),
  timestamp: fc.integer({ min: 1_000_000_000_000, max: 2_000_000_000_000 }),
  metadata: fc.option(
    fc.dictionary(fc.string({ minLength: 1, maxLength: 10 }), fc.string({ maxLength: 20 })),
    { nil: undefined },
  ),
});

const messagesArb = fc.array(messageArb, { minLength: 0, maxLength: 30 });

const filtersArb: fc.Arbitrary<SearchFilters> = fc.record({
  keyword: fc.string({ minLength: 0, maxLength: 20 }),
  role: fc.option(fc.constantFrom('user' as const, 'assistant' as const, 'all' as const), { nil: undefined }),
  dateRange: fc.option(
    fc.tuple(
      fc.integer({ min: 1_000_000_000_000, max: 1_500_000_000_000 }),
      fc.integer({ min: 1_500_000_000_001, max: 2_000_000_000_000 }),
    ),
    { nil: undefined },
  ),
  hasMetadata: fc.option(fc.boolean(), { nil: undefined }),
});

// ── Tests ────────────────────────────────────────────

describe('searchMessages — Property-Based Tests', () => {
  it('Property 5: results are a subset of input messages', () => {
    fc.assert(
      fc.property(messagesArb, filtersArb, (messages, filters) => {
        const results = searchMessages(messages, filters);
        const inputIds = new Set(messages.map((m) => m.id));
        for (const r of results) {
          expect(inputIds.has(r.messageId)).toBe(true);
        }
      }),
    );
  });

  it('Property 6: results preserve original message order', () => {
    fc.assert(
      fc.property(messagesArb, filtersArb, (messages, filters) => {
        const results = searchMessages(messages, filters);
        const idToIndex = new Map(messages.map((m, i) => [m.id, i]));

        for (let i = 1; i < results.length; i++) {
          const prevIdx = idToIndex.get(results[i - 1].messageId)!;
          const currIdx = idToIndex.get(results[i].messageId)!;
          expect(currIdx).toBeGreaterThan(prevIdx);
        }
      }),
    );
  });

  it('Property 7: empty keyword with no other filters returns all messages', () => {
    fc.assert(
      fc.property(messagesArb, (messages) => {
        const filters: SearchFilters = { keyword: '' };
        const results = searchMessages(messages, filters);
        expect(results.length).toBe(messages.length);
      }),
    );
  });

  it('Property 8: all highlight positions are valid (0 <= start < end <= content.length)', () => {
    fc.assert(
      fc.property(messagesArb, filtersArb, (messages, filters) => {
        const results = searchMessages(messages, filters);
        const msgMap = new Map(messages.map((m) => [m.id, m]));

        for (const r of results) {
          const msg = msgMap.get(r.messageId)!;
          for (const [start, end] of r.matchPositions) {
            expect(start).toBeGreaterThanOrEqual(0);
            expect(end).toBeGreaterThan(start);
            expect(end).toBeLessThanOrEqual(msg.content.length);
          }
        }
      }),
    );
  });

  it('Role filter: results only contain messages with matching role', () => {
    fc.assert(
      fc.property(
        messagesArb,
        fc.constantFrom('user' as const, 'assistant' as const),
        (messages, role) => {
          const filters: SearchFilters = { keyword: '', role };
          const results = searchMessages(messages, filters);
          const resultIds = new Set(results.map((r) => r.messageId));

          for (const msg of messages) {
            if (resultIds.has(msg.id)) {
              expect(msg.role).toBe(role);
            }
          }
        },
      ),
    );
  });

  it('Role filter: all messages with matching role are included (no false negatives with empty keyword)', () => {
    fc.assert(
      fc.property(
        messagesArb,
        fc.constantFrom('user' as const, 'assistant' as const),
        (messages, role) => {
          const filters: SearchFilters = { keyword: '', role };
          const results = searchMessages(messages, filters);
          const resultIds = new Set(results.map((r) => r.messageId));

          for (const msg of messages) {
            if (msg.role === role) {
              expect(resultIds.has(msg.id)).toBe(true);
            }
          }
        },
      ),
    );
  });

  it('Date range filter: results only contain messages within range', () => {
    fc.assert(
      fc.property(
        messagesArb,
        fc.tuple(
          fc.integer({ min: 1_000_000_000_000, max: 1_500_000_000_000 }),
          fc.integer({ min: 1_500_000_000_001, max: 2_000_000_000_000 }),
        ),
        (messages, [start, end]) => {
          const filters: SearchFilters = { keyword: '', dateRange: [start, end] };
          const results = searchMessages(messages, filters);
          const resultIds = new Set(results.map((r) => r.messageId));

          for (const msg of messages) {
            if (resultIds.has(msg.id)) {
              expect(msg.timestamp).toBeGreaterThanOrEqual(start);
              expect(msg.timestamp).toBeLessThanOrEqual(end);
            }
          }
        },
      ),
    );
  });

  it('Keyword match: every result contains the keyword (case-insensitive)', () => {
    fc.assert(
      fc.property(
        messagesArb,
        fc.string({ minLength: 1, maxLength: 5 }),
        (messages, keyword) => {
          const filters: SearchFilters = { keyword };
          const results = searchMessages(messages, filters);
          const msgMap = new Map(messages.map((m) => [m.id, m]));

          for (const r of results) {
            const msg = msgMap.get(r.messageId)!;
            expect(msg.content.toLowerCase()).toContain(keyword.toLowerCase().trim());
          }
        },
      ),
    );
  });
});
