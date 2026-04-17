/**
 * Unit tests for AgentExecutionPanel rendering.
 *
 * Tests collapsed/expanded states and event display content.
 *
 * Validates: Requirements 15.2, 15.4
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import React, { useState } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { act } from 'react';

// ── Inline types matching src/api.ts AgentEvent ──

interface AgentEvent {
  event: 'node_start' | 'node_end' | 'tool_call';
  node?: string;
  tool?: string;
  duration_ms?: number;
  timestamp: number;
}

// ── Inline copy of AgentExecutionPanel from App.tsx ──

const nodeLabels: Record<string, string> = {
  supervisor: '🧭 路由决策',
  worker: '⚙️ 任务执行',
  reviewer: '✅ 质量审核',
  tool: '🔧 工具调用',
};

function AgentExecutionPanel({ events }: { events: AgentEvent[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!events || events.length === 0) return null;

  const steps: { label: string; detail?: string; durationMs?: number }[] = [];
  for (const evt of events) {
    if (evt.event === 'node_end' && evt.node) {
      steps.push({
        label: nodeLabels[evt.node] || evt.node,
        durationMs: evt.duration_ms,
      });
    } else if (evt.event === 'tool_call' && evt.tool) {
      steps.push({
        label: '🔧 ' + evt.tool,
        durationMs: evt.duration_ms,
      });
    }
  }

  if (steps.length === 0) return null;

  return (
    <div className="agent-exec-panel">
      <button
        className="agent-exec-toggle"
        onClick={() => setExpanded(prev => !prev)}
        aria-expanded={expanded}
        aria-label="展开/折叠执行详情"
      >
        <span className="agent-exec-toggle-icon">{expanded ? '▾' : '▸'}</span>
        <span className="agent-exec-toggle-text">执行过程 · {steps.length} 步</span>
      </button>
      {expanded && (
        <div className="agent-exec-steps">
          {steps.map((step, i) => (
            <div key={i} className="agent-exec-step">
              <span className="agent-exec-step-dot" />
              <span className="agent-exec-step-label">{step.label}</span>
              {step.durationMs != null && (
                <span className="agent-exec-step-duration">{step.durationMs}ms</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Test helpers ──

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(element: React.ReactElement) {
  act(() => root.render(element));
}

function getToggleButton(): HTMLButtonElement | null {
  return container.querySelector('.agent-exec-toggle');
}

function getStepsContainer(): HTMLDivElement | null {
  return container.querySelector('.agent-exec-steps');
}

function clickToggle() {
  const btn = getToggleButton();
  if (btn) act(() => btn.click());
}

// ── Sample events ──

const sampleEvents: AgentEvent[] = [
  { event: 'node_start', node: 'supervisor', timestamp: 1000 },
  { event: 'node_end', node: 'supervisor', duration_ms: 120, timestamp: 1120 },
  { event: 'node_start', node: 'worker', timestamp: 1120 },
  { event: 'tool_call', tool: 'search_knowledge_tool', duration_ms: 85, timestamp: 1200 },
  { event: 'node_end', node: 'worker', duration_ms: 200, timestamp: 1320 },
  { event: 'node_end', node: 'reviewer', duration_ms: 50, timestamp: 1370 },
];

// ── Collapsed/expanded state tests (Requirement 15.4) ──

describe('AgentExecutionPanel collapsed/expanded states', () => {
  it('renders in collapsed state by default (steps NOT visible)', () => {
    render(<AgentExecutionPanel events={sampleEvents} />);

    expect(getToggleButton()).not.toBeNull();
    expect(getStepsContainer()).toBeNull();
  });

  it('expands when toggle button is clicked (steps become visible)', () => {
    render(<AgentExecutionPanel events={sampleEvents} />);

    clickToggle();

    expect(getStepsContainer()).not.toBeNull();
    const steps = container.querySelectorAll('.agent-exec-step');
    expect(steps.length).toBeGreaterThan(0);
  });

  it('collapses again when toggle is clicked a second time', () => {
    render(<AgentExecutionPanel events={sampleEvents} />);

    clickToggle(); // expand
    expect(getStepsContainer()).not.toBeNull();

    clickToggle(); // collapse
    expect(getStepsContainer()).toBeNull();
  });

  it('has correct aria-expanded attribute', () => {
    render(<AgentExecutionPanel events={sampleEvents} />);

    const btn = getToggleButton()!;
    expect(btn.getAttribute('aria-expanded')).toBe('false');

    clickToggle();
    expect(btn.getAttribute('aria-expanded')).toBe('true');

    clickToggle();
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('shows correct step count in toggle text', () => {
    render(<AgentExecutionPanel events={sampleEvents} />);

    const toggleText = container.querySelector('.agent-exec-toggle-text');
    // sampleEvents has 4 displayable steps: supervisor node_end, tool_call, worker node_end, reviewer node_end
    expect(toggleText?.textContent).toBe('执行过程 · 4 步');
  });
});

// ── Event display content tests (Requirement 15.2) ──

describe('AgentExecutionPanel event display content', () => {
  it('displays node_end events with correct nodeLabels mapping', () => {
    const events: AgentEvent[] = [
      { event: 'node_end', node: 'supervisor', duration_ms: 100, timestamp: 1000 },
      { event: 'node_end', node: 'worker', duration_ms: 200, timestamp: 2000 },
      { event: 'node_end', node: 'reviewer', duration_ms: 50, timestamp: 3000 },
      { event: 'node_end', node: 'tool', duration_ms: 30, timestamp: 4000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const labels = container.querySelectorAll('.agent-exec-step-label');
    expect(labels[0].textContent).toBe('🧭 路由决策');
    expect(labels[1].textContent).toBe('⚙️ 任务执行');
    expect(labels[2].textContent).toBe('✅ 质量审核');
    expect(labels[3].textContent).toBe('🔧 工具调用');
  });

  it('displays tool_call events with 🔧 prefix + tool name', () => {
    const events: AgentEvent[] = [
      { event: 'tool_call', tool: 'search_knowledge_tool', duration_ms: 85, timestamp: 1000 },
      { event: 'tool_call', tool: 'query_order_tool', duration_ms: 40, timestamp: 2000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const labels = container.querySelectorAll('.agent-exec-step-label');
    expect(labels[0].textContent).toBe('🔧 search_knowledge_tool');
    expect(labels[1].textContent).toBe('🔧 query_order_tool');
  });

  it('displays duration when present', () => {
    const events: AgentEvent[] = [
      { event: 'node_end', node: 'supervisor', duration_ms: 120, timestamp: 1000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const duration = container.querySelector('.agent-exec-step-duration');
    expect(duration).not.toBeNull();
    expect(duration!.textContent).toBe('120ms');
  });

  it('does NOT display duration when absent', () => {
    const events: AgentEvent[] = [
      { event: 'node_end', node: 'supervisor', timestamp: 1000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const duration = container.querySelector('.agent-exec-step-duration');
    expect(duration).toBeNull();
  });

  it('filters out node_start events (not shown as steps)', () => {
    const events: AgentEvent[] = [
      { event: 'node_start', node: 'supervisor', timestamp: 1000 },
      { event: 'node_start', node: 'worker', timestamp: 2000 },
      { event: 'node_end', node: 'supervisor', duration_ms: 100, timestamp: 3000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const steps = container.querySelectorAll('.agent-exec-step');
    expect(steps.length).toBe(1);
    const label = container.querySelector('.agent-exec-step-label');
    expect(label!.textContent).toBe('🧭 路由决策');
  });

  it('falls back to raw node name for unknown nodes', () => {
    const events: AgentEvent[] = [
      { event: 'node_end', node: 'custom_analyzer', duration_ms: 75, timestamp: 1000 },
    ];
    render(<AgentExecutionPanel events={events} />);
    clickToggle();

    const label = container.querySelector('.agent-exec-step-label');
    expect(label!.textContent).toBe('custom_analyzer');
  });

  it('renders nothing when events array is empty', () => {
    render(<AgentExecutionPanel events={[]} />);

    expect(container.querySelector('.agent-exec-panel')).toBeNull();
    expect(getToggleButton()).toBeNull();
  });

  it('renders nothing when events contain only node_start events', () => {
    const events: AgentEvent[] = [
      { event: 'node_start', node: 'supervisor', timestamp: 1000 },
      { event: 'node_start', node: 'worker', timestamp: 2000 },
    ];
    render(<AgentExecutionPanel events={events} />);

    expect(container.querySelector('.agent-exec-panel')).toBeNull();
    expect(getToggleButton()).toBeNull();
  });
});
