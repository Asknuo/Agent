/**
 * Conversation export module.
 *
 * Provides JSON and PDF export for chat conversations,
 * plus utility helpers for building printable HTML and triggering downloads.
 */

import type { ChatMetadata, AgentEvent } from './api';
import type { Locale } from './i18n';

// ── Types ────────────────────────────────────────────

/** Input message shape (compatible with ChatMessage in App.tsx) */
export interface ExportableMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: ChatMetadata;
  agentEvents?: AgentEvent[];
}

export interface ExportOptions {
  format: 'pdf' | 'json';
  includeMetadata: boolean;
  includeAgentEvents: boolean;
  dateRange?: [number, number];
}

export interface ExportedMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string; // ISO 8601
  metadata?: ChatMetadata;
  agentEvents?: AgentEvent[];
}

export interface ExportedConversation {
  version: '1.0';
  exportedAt: string; // ISO 8601
  sessionId?: string;
  locale: Locale;
  messageCount: number;
  messages: ExportedMessage[];
}

// ── JSON Export ──────────────────────────────────────

/**
 * Serialises messages into an ExportedConversation JSON string.
 */
export function exportToJSON(
  messages: ExportableMessage[],
  sessionId: string | undefined,
  options: ExportOptions,
  locale: Locale = 'zh-CN',
): string {
  const exported: ExportedConversation = {
    version: '1.0',
    exportedAt: new Date().toISOString(),
    sessionId,
    locale,
    messageCount: messages.length,
    messages: messages.map((msg) => {
      const entry: ExportedMessage = {
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp).toISOString(),
      };
      if (options.includeMetadata && msg.metadata) {
        entry.metadata = msg.metadata;
      }
      if (options.includeAgentEvents && msg.agentEvents) {
        entry.agentEvents = msg.agentEvents;
      }
      return entry;
    }),
  };

  return JSON.stringify(exported, null, 2);
}


// ── Printable HTML Builder ──────────────────────────

/** Escapes HTML special characters to prevent XSS. */
function escapeHTML(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Builds a self-contained printable HTML document for the conversation.
 */
export function buildPrintableHTML(
  messages: ExportableMessage[],
  sessionId: string | undefined,
  options: ExportOptions,
): string {
  const now = new Date().toLocaleString();
  const rows = messages
    .map((msg) => {
      const roleLabel = msg.role === 'user' ? '用户' : '助手';
      const time = new Date(msg.timestamp).toLocaleString();
      let metaHTML = '';
      if (options.includeMetadata && msg.metadata) {
        metaHTML = `<div class="meta">${escapeHTML(JSON.stringify(msg.metadata))}</div>`;
      }
      let eventsHTML = '';
      if (options.includeAgentEvents && msg.agentEvents?.length) {
        eventsHTML = `<div class="events">${escapeHTML(JSON.stringify(msg.agentEvents))}</div>`;
      }
      return `<div class="msg ${msg.role}">
        <div class="role">${escapeHTML(roleLabel)}</div>
        <div class="content">${escapeHTML(msg.content)}</div>
        <div class="time">${escapeHTML(time)}</div>
        ${metaHTML}${eventsHTML}
      </div>`;
    })
    .join('\n');

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>对话导出</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:800px;margin:0 auto;padding:20px}
  h1{font-size:18px} .info{color:#888;font-size:12px;margin-bottom:16px}
  .msg{margin:8px 0;padding:10px;border-radius:8px;border:1px solid #eee}
  .msg.user{background:#e6f7ff} .msg.assistant{background:#f6ffed}
  .role{font-weight:bold;margin-bottom:4px} .time{color:#999;font-size:11px;margin-top:4px}
  .meta,.events{font-size:11px;color:#666;margin-top:4px;word-break:break-all}
</style></head><body>
<h1>对话记录</h1>
<div class="info">会话 ID: ${escapeHTML(sessionId ?? '未知')} | 导出时间: ${escapeHTML(now)} | 消息数: ${messages.length}</div>
${rows}
</body></html>`;
}

// ── PDF Export (iframe + print) ─────────────────────

/**
 * Opens a hidden iframe with the printable HTML and triggers window.print().
 */
export function exportToPDF(
  messages: ExportableMessage[],
  sessionId: string | undefined,
  options: ExportOptions,
): void {
  const html = buildPrintableHTML(messages, sessionId, options);

  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.left = '-9999px';
  iframe.style.top = '-9999px';
  iframe.style.width = '0';
  iframe.style.height = '0';
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!doc) {
    document.body.removeChild(iframe);
    return;
  }

  doc.open();
  doc.write(html);
  doc.close();

  const win = iframe.contentWindow;
  if (!win) {
    document.body.removeChild(iframe);
    return;
  }

  const cleanup = () => {
    try {
      document.body.removeChild(iframe);
    } catch {
      // already removed
    }
  };

  win.onafterprint = cleanup;
  // Fallback: remove after a timeout in case onafterprint doesn't fire
  setTimeout(cleanup, 60_000);
  win.print();
}

// ── Download Utility ────────────────────────────────

/**
 * Triggers a browser download for the given Blob.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
