/** API 客户端 */
const BASE = '/api';

export interface ChatMetadata {
  sentiment?: string;
  intent?: string;
  confidence?: number;
  language?: string;
  toolsUsed?: string[];
  knowledgeRefs?: string[];
  responseTimeMs?: number;
}

export interface ChatResponse {
  sessionId: string;
  reply: string;
  metadata: ChatMetadata;
}

/** 流式发送消息，通过回调逐块接收 */
export async function sendMessageStream(
  message: string,
  sessionId: string | undefined,
  onSessionId: (id: string) => void,
  onChunk: (text: string) => void,
  onMetadata: (meta: ChatMetadata) => void,
  onDone: () => void,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, user_id: 'web-user' }),
  });

  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;

      try {
        const evt = JSON.parse(raw);
        switch (evt.type) {
          case 'session':
            onSessionId(evt.sessionId);
            break;
          case 'chunk':
            onChunk(evt.content);
            break;
          case 'metadata':
            onMetadata(evt.metadata);
            break;
          case 'done':
            onDone();
            break;
        }
      } catch {
        // ignore malformed lines
      }
    }
  }
}

export async function rateSession(sessionId: string, rating: number): Promise<void> {
  await fetch(`${BASE}/sessions/${sessionId}/rate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  });
}

/** 指标数据结构 */
export interface MetricEntry {
  name: string;
  type: string;
  help: string;
  samples: { labels: Record<string, string>; value: number }[];
}

/** 拉取并解析 /metrics 端点的 Prometheus 文本 */
export async function fetchMetrics(): Promise<MetricEntry[]> {
  const res = await fetch('/metrics');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const text = await res.text();
  return parsePrometheusText(text);
}

function parsePrometheusText(text: string): MetricEntry[] {
  const metrics: MetricEntry[] = [];
  let current: MetricEntry | null = null;

  for (const line of text.split('\n')) {
    if (line.startsWith('# HELP ')) {
      const rest = line.slice(7);
      const idx = rest.indexOf(' ');
      const name = rest.slice(0, idx);
      const help = rest.slice(idx + 1);
      current = { name, type: '', help, samples: [] };
      metrics.push(current);
    } else if (line.startsWith('# TYPE ')) {
      const rest = line.slice(7);
      const idx = rest.indexOf(' ');
      const type = rest.slice(idx + 1);
      if (current) current.type = type;
    } else if (line && !line.startsWith('#') && current) {
      const match = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)\{?(.*?)\}?\s+([\d.eE+-]+|NaN|Inf|\+Inf|-Inf)$/);
      if (match) {
        const labels: Record<string, string> = {};
        if (match[2]) {
          for (const pair of match[2].split(',')) {
            const eqIdx = pair.indexOf('=');
            if (eqIdx > 0) {
              labels[pair.slice(0, eqIdx)] = pair.slice(eqIdx + 1).replace(/"/g, '');
            }
          }
        }
        current.samples.push({ labels, value: parseFloat(match[3]) });
      }
    }
  }
  return metrics;
}
