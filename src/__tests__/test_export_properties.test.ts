/**
 * Property-Based Tests for the export module.
 *
 * Validates:
 * - Correctness Property 9:  JSON export reversibility — JSON.parse(exportToJSON(...)) returns valid ExportedConversation
 * - Correctness Property 10: Export message count consistency — exported.messageCount === exported.messages.length
 * - Correctness Property 11: Metadata inclusion control — when includeMetadata === false, no message has metadata field
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import {
  exportToJSON,
  ExportableMessage,
  ExportOptions,
  ExportedConversation,
} from '../export';
import type { Locale } from '../i18n';
import type { ChatMetadata, AgentEvent } from '../api';

// ── Arbitraries ──────────────────────────────────────

const localeArb: fc.Arbitrary<Locale> = fc.constantFrom('zh-CN', 'en-US');

const agentEventArb: fc.Arbitrary<AgentEvent> = fc.record({
  event: fc.constantFrom('node_start' as const, 'node_end' as const, 'tool_call' as const),
  node: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
  tool: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
  duration_ms: fc.option(fc.nat({ max: 10000 }), { nil: undefined }),
  timestamp: fc.integer({ min: 1_000_000_000_000, max: 2_000_000_000_000 }),
});

const chatMetadataArb: fc.Arbitrary<ChatMetadata> = fc.record({
  sentiment: fc.option(fc.constantFrom('positive', 'negative', 'neutral'), { nil: undefined }),
  intent: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
  confidence: fc.option(fc.double({ min: 0, max: 1, noNaN: true }), { nil: undefined }),
  language: fc.option(fc.constantFrom('zh', 'en'), { nil: undefined }),
  toolsUsed: fc.option(fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 3 }), { nil: undefined }),
  knowledgeRefs: fc.option(fc.array(fc.string({ minLength: 1, maxLength: 30 }), { maxLength: 3 }), { nil: undefined }),
  responseTimeMs: fc.option(fc.nat({ max: 5000 }), { nil: undefined }),
  traceId: fc.option(fc.uuid(), { nil: undefined }),
  agentEvents: fc.option(fc.array(agentEventArb, { maxLength: 3 }), { nil: undefined }),
});

const messageArb: fc.Arbitrary<ExportableMessage> = fc.record({
  id: fc.uuid(),
  role: fc.constantFrom('user' as const, 'assistant' as const),
  content: fc.string({ minLength: 0, maxLength: 200 }),
  timestamp: fc.integer({ min: 1_000_000_000_000, max: 2_000_000_000_000 }),
  metadata: fc.option(chatMetadataArb, { nil: undefined }),
  agentEvents: fc.option(fc.array(agentEventArb, { maxLength: 3 }), { nil: undefined }),
});

const messagesArb = fc.array(messageArb, { minLength: 0, maxLength: 20 });

const sessionIdArb: fc.Arbitrary<string | undefined> = fc.option(
  fc.uuid(),
  { nil: undefined },
);

// ── Property Tests ───────────────────────────────────

describe('Property 9: JSON export reversibility', () => {
  /**
   * **Validates: Requirements 2.1**
   *
   * For any array of messages, exportToJSON produces a valid JSON string
   * that parses into a well-formed ExportedConversation object.
   */
  it('JSON.parse(exportToJSON(...)) returns a valid ExportedConversation', () => {
    fc.assert(
      fc.property(
        messagesArb,
        sessionIdArb,
        fc.boolean(),
        fc.boolean(),
        localeArb,
        (messages, sessionId, includeMeta, includeEvents, locale) => {
          const options: ExportOptions = {
            format: 'json',
            includeMetadata: includeMeta,
            includeAgentEvents: includeEvents,
          };

          const json = exportToJSON(messages, sessionId, options, locale);

          // Must be parseable
          const parsed: ExportedConversation = JSON.parse(json);

          // Structural checks
          expect(parsed.version).toBe('1.0');
          expect(typeof parsed.exportedAt).toBe('string');
          expect(new Date(parsed.exportedAt).toISOString()).toBe(parsed.exportedAt);
          expect(parsed.locale).toBe(locale);
          expect(Array.isArray(parsed.messages)).toBe(true);
          expect(typeof parsed.messageCount).toBe('number');

          // Each exported message has required fields
          for (const msg of parsed.messages) {
            expect(['user', 'assistant']).toContain(msg.role);
            expect(typeof msg.content).toBe('string');
            expect(typeof msg.timestamp).toBe('string');
            // timestamp must be valid ISO 8601
            expect(new Date(msg.timestamp).toISOString()).toBe(msg.timestamp);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe('Property 10: Export message count consistency', () => {
  /**
   * **Validates: Requirements 2.1**
   *
   * exported.messageCount always equals exported.messages.length.
   */
  it('messageCount matches messages array length', () => {
    fc.assert(
      fc.property(
        messagesArb,
        sessionIdArb,
        fc.boolean(),
        fc.boolean(),
        localeArb,
        (messages, sessionId, includeMeta, includeEvents, locale) => {
          const options: ExportOptions = {
            format: 'json',
            includeMetadata: includeMeta,
            includeAgentEvents: includeEvents,
          };

          const json = exportToJSON(messages, sessionId, options, locale);
          const parsed: ExportedConversation = JSON.parse(json);

          expect(parsed.messageCount).toBe(parsed.messages.length);
          expect(parsed.messageCount).toBe(messages.length);
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe('Property 11: Metadata inclusion control', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * When includeMetadata is false, no exported message contains a metadata field.
   * When includeAgentEvents is false, no exported message contains an agentEvents field.
   */
  it('includeMetadata=false excludes metadata from all messages', () => {
    fc.assert(
      fc.property(
        messagesArb,
        sessionIdArb,
        localeArb,
        (messages, sessionId, locale) => {
          const options: ExportOptions = {
            format: 'json',
            includeMetadata: false,
            includeAgentEvents: true,
          };

          const json = exportToJSON(messages, sessionId, options, locale);
          const parsed: ExportedConversation = JSON.parse(json);

          for (const msg of parsed.messages) {
            expect(msg.metadata).toBeUndefined();
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('includeAgentEvents=false excludes agentEvents from all messages', () => {
    fc.assert(
      fc.property(
        messagesArb,
        sessionIdArb,
        localeArb,
        (messages, sessionId, locale) => {
          const options: ExportOptions = {
            format: 'json',
            includeMetadata: true,
            includeAgentEvents: false,
          };

          const json = exportToJSON(messages, sessionId, options, locale);
          const parsed: ExportedConversation = JSON.parse(json);

          for (const msg of parsed.messages) {
            expect(msg.agentEvents).toBeUndefined();
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
