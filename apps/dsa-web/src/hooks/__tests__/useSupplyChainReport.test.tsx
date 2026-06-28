import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const generateStream = vi.hoisted(() => vi.fn());
vi.mock('../../api/supplyChainReports', () => ({
  supplyChainReportApi: { generateStream },
}));

import { useSupplyChainReport } from '../useSupplyChainReport';

const encoder = new TextEncoder();

/** 构造一个一次性 SSE Response（同步 enqueue 所有行后 close）。每行按真实 SSE 用 \n\n 终止。 */
function createStreamResponse(lines: string[]): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(lines.map((l) => l + '\n\n').join('')));
        controller.close();
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

/** 构造一个永不 enqueue、永不 close 的 Response（模拟断线/挂起）。 */
function createStalledResponse(): Response {
  return new Response(
    new ReadableStream({
      start() {
        // 故意什么都不做
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

function data(line: object): string {
  return `data: ${JSON.stringify(line)}`;
}

describe('useSupplyChainReport', () => {
  beforeEach(() => {
    generateStream.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('done 事件（带 report_id）→ status done，report 含 topic/markdown', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([
        data({ type: 'thinking', step: 1, message: '调研中' }),
        data({ type: 'tool_done', tool: 'score_supply_chain_bottleneck', display_name: '瓶颈打分', success: true }),
        data({ type: 'done', success: true, report_id: 'sc_202606271530_1', status: 'success', markdown: '# 报告', total_steps: 24 }),
      ]),
    );

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('光模块产业链', 'CPO 上游');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.reportId).toBe('sc_202606271530_1');
    expect(result.current.report?.markdown).toBe('# 报告');
    expect(result.current.report?.topic).toBe('光模块产业链');
    expect(result.current.report?.research_hint).toBe('CPO 上游');
    expect(result.current.report?.status).toBe('success');
    expect(result.current.progressSteps).toHaveLength(2);
  });

  it('done 事件无 report_id → status error', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'done', success: false, report_id: null, message: '生成失败' })]),
    );

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('生成失败');
  });

  it('error 事件 → status error', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'error', message: '后端炸了' })]),
    );

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('后端炸了');
  });

  it('heartbeat 不进入进度步骤（仅重置 watchdog）', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([
        data({ type: 'heartbeat' }),
        data({ type: 'heartbeat' }),
        data({ type: 'done', success: true, report_id: 'sc_x', markdown: '# x' }),
      ]),
    );

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(result.current.progressSteps).toHaveLength(0);
    expect(result.current.status).toBe('done');
  });

  it('thinking/tool_start/generating 进入进度步骤', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([
        data({ type: 'thinking', message: '分析' }),
        data({ type: 'tool_start', tool: 't', display_name: '工具' }),
        data({ type: 'generating', message: '生成中' }),
        data({ type: 'done', success: true, report_id: 'sc_x', markdown: '# x' }),
      ]),
    );

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(result.current.progressSteps.map((s) => s.type)).toEqual([
      'thinking',
      'tool_start',
      'generating',
    ]);
  });

  it('SSE 提前关闭无 done/error → status error（提示去历史列表）', async () => {
    generateStream.mockResolvedValueOnce(createStreamResponse([data({ type: 'thinking', message: 'x' })]));

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('历史列表');
  });

  it('90s watchdog：挂起连接 → 超时中断 error', async () => {
    vi.useFakeTimers();
    generateStream.mockReturnValueOnce(createStalledResponse());

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      result.current.generate('主题');
      await vi.advanceTimersByTimeAsync(90_000);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('连接超时中断');
  });

  it('cancel 取消生成 → status idle', async () => {
    generateStream.mockReturnValueOnce(createStalledResponse());

    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      result.current.generate('主题');
    });
    expect(result.current.status).toBe('generating');

    act(() => {
      result.current.cancel();
    });
    expect(result.current.status).toBe('idle');
  });

  it('reset 清空全部状态', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'done', success: true, report_id: 'sc_x', markdown: '# x' })]),
    );
    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });
    expect(result.current.report).not.toBeNull();

    act(() => {
      result.current.reset();
    });
    expect(result.current.status).toBe('idle');
    expect(result.current.report).toBeNull();
    expect(result.current.reportId).toBeNull();
    expect(result.current.progressSteps).toHaveLength(0);
  });

  it('卸载时清理不抛错', async () => {
    generateStream.mockReturnValueOnce(createStalledResponse());
    const { result, unmount } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      result.current.generate('主题');
    });
    expect(() => unmount()).not.toThrow();
  });

  it('generateStream 传 signal（AbortController）', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'done', success: true, report_id: 'sc_x', markdown: '# x' })]),
    );
    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });

    expect(generateStream).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('SSE 流不可用（response 无 body）→ error', async () => {
    generateStream.mockResolvedValueOnce({ ok: true } as Response);
    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('SSE 流不可用');
  });

  it('generateStream 非 abort 网络错误 → error 带 message', async () => {
    generateStream.mockRejectedValueOnce(new Error('网络断了'));
    const { result } = renderHook(() => useSupplyChainReport());
    await act(async () => {
      await result.current.generate('主题');
    });
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('网络断了');
  });

  it('等待 generating 状态切到 done（waitFor 行为验证）', async () => {
    generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'done', success: true, report_id: 'sc_x', markdown: '# x' })]),
    );
    const { result } = renderHook(() => useSupplyChainReport());

    await act(async () => {
      result.current.generate('主题');
    });

    await waitFor(() => expect(result.current.status).toBe('done'));
  });
});
