/**
 * Property 18: localStorage round trip
 *
 * For any valid list of ChatMessage objects with arbitrary field values,
 * saving to localStorage via saveSessionToStorage and then loading via
 * loadSessionFromStorage SHALL preserve all message fields exactly.
 *
 * Validates: Requirement 12.3
 */

import { describe, it, expect, beforeEach } from 'vitest';
import * as fc from 'fast-check';

// ── Inline types matching App.tsx ChatMessage & ChatMetadata ──

interface ChatMetadata {
  sentiment?: string;
  intent?: string;
  confidence?: number;
  language?: string;
  toolsUsed?: string[];
  knowledgeRefs?: string[];
  responseTimeMs?: number;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: ChatMetadata;
  status?: 'sending' | 'sent' | 'failed';
}

// ── Reproduce save/load logic from App.tsx ──

const SESSION_STORAGE_KEY = 'xiaozhi_session';

function saveSessionToStorage(sessionId: string | undefined, messages: ChatMessage[]) {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessionId, messages }));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

function loadSessionFromStorage(): { sessionId: string | undefined; messages: ChatMessage[] } | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.messages)) return parsed;
    return null;
  } catch {
    return null;
  }
}

// ── Arbitraries ──

const metadataArb: fc.Arbitrary<ChatMetadata> = fc.record(
  {
    sentiment: fc.string(),
    intent: fc.string(),
    confidence: fc.double({ min: 0, max: 1, noNaN: true }),
    language: fc.string(),
    toolsUsed: fc.array(fc.string(), { maxLength: 5 }),
    knowledgeRefs: fc.array(fc.string(), { maxLength: 5 }),
    responseTimeMs: fc.integer({ min: 0, max: 100_000 }),
  },
  { requiredKeys: [] },
);

const chatMessageArb: fc.Arbitrary<ChatMessage> = fc.record({
  id: fc.uuid(),
  role: fc.constantFrom('user' as const, 'assistant' as const),
  content: fc.string(),
  timestamp: fc.integer({ min: 0, max: 2_000_000_000_000 }),
  metadata: fc.option(metadataArb, { nil: undefined }),
  status: fc.option(
    fc.constantFrom('sending' as const, 'sent' as const, 'failed' as const),
    { nil: undefined },
  ),
});

const sessionIdArb: fc.Arbitrary<string | undefined> = fc.option(fc.uuid(), { nil: undefined });

// ── localStorage mock (jsdom provides one, but reset between tests) ──

beforeEach(() => {
  localStorage.clear();
});

// ── Property Tests ──

describe('Property 18: localStorage round trip', () => {
  it('save then load preserves sessionId and all message fields', () => {
    fc.assert(
      fc.property(
        sessionIdArb,
        fc.array(chatMessageArb, { maxLength: 30 }),
        (sessionId, messages) => {
          saveSessionToStorage(sessionId, messages);
          const loaded = loadSessionFromStorage();

          expect(loaded).not.toBeNull();
          expect(loaded!.sessionId).toEqual(sessionId);
          expect(loaded!.messages).toHaveLength(messages.length);

          for (let i = 0; i < messages.length; i++) {
            const orig = messages[i];
            const restored = loaded!.messages[i];

            expect(restored.id).toBe(orig.id);
            expect(restored.role).toBe(orig.role);
            expect(restored.content).toBe(orig.content);
            expect(restored.timestamp).toBe(orig.timestamp);
            expect(restored.status).toBe(orig.status);

            // metadata deep equality (handles undefined correctly)
            expect(restored.metadata).toEqual(orig.metadata);
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it('load returns null when nothing has been saved', () => {
    const loaded = loadSessionFromStorage();
    expect(loaded).toBeNull();
  });

  it('latest save overwrites previous save', () => {
    fc.assert(
      fc.property(
        sessionIdArb,
        fc.array(chatMessageArb, { minLength: 1, maxLength: 10 }),
        sessionIdArb,
        fc.array(chatMessageArb, { minLength: 1, maxLength: 10 }),
        (sid1, msgs1, sid2, msgs2) => {
          saveSessionToStorage(sid1, msgs1);
          saveSessionToStorage(sid2, msgs2);

          const loaded = loadSessionFromStorage();
          expect(loaded).not.toBeNull();
          expect(loaded!.sessionId).toEqual(sid2);
          expect(loaded!.messages).toHaveLength(msgs2.length);
          expect(loaded!.messages).toEqual(msgs2);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('empty message array round trips correctly', () => {
    fc.assert(
      fc.property(sessionIdArb, (sessionId) => {
        saveSessionToStorage(sessionId, []);
        const loaded = loadSessionFromStorage();

        expect(loaded).not.toBeNull();
        expect(loaded!.sessionId).toEqual(sessionId);
        expect(loaded!.messages).toEqual([]);
      }),
      { numRuns: 50 },
    );
  });

  it('messages with all optional fields undefined round trip correctly', () => {
    const minimalMessage: ChatMessage = {
      id: 'test-id',
      role: 'user',
      content: 'hello',
      timestamp: Date.now(),
      metadata: undefined,
      status: undefined,
    };

    saveSessionToStorage('session-1', [minimalMessage]);
    const loaded = loadSessionFromStorage();

    expect(loaded).not.toBeNull();
    expect(loaded!.messages[0].id).toBe(minimalMessage.id);
    expect(loaded!.messages[0].role).toBe(minimalMessage.role);
    expect(loaded!.messages[0].content).toBe(minimalMessage.content);
    expect(loaded!.messages[0].timestamp).toBe(minimalMessage.timestamp);
  });

  it('messages with full metadata round trip correctly', () => {
    fc.assert(
      fc.property(chatMessageArb, (msg) => {
        // Force metadata to be present
        const withMeta: ChatMessage = {
          ...msg,
          metadata: {
            sentiment: 'positive',
            intent: 'product_inquiry',
            confidence: 0.95,
            language: 'zh',
            toolsUsed: ['search_knowledge_tool', 'query_order_tool'],
            knowledgeRefs: ['doc1.md', 'doc2.md'],
            responseTimeMs: 150,
          },
        };

        saveSessionToStorage('s1', [withMeta]);
        const loaded = loadSessionFromStorage();

        expect(loaded).not.toBeNull();
        expect(loaded!.messages[0].metadata).toEqual(withMeta.metadata);
      }),
      { numRuns: 50 },
    );
  });
});
