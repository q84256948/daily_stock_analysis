import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { usePolicyMinesweeper } from '../usePolicyMinesweeper';

const { generateStream } = vi.hoisted(() => ({
  generateStream: vi.fn(),
}));

vi.mock('../../api/policyMinesweeper', () => ({
  policyMinesweeperApi: { generateStream },
}));

/** 构造一个发射指定 SSE 事件行的真实 ReadableStream（jsdom 原生支持）。 */
function makeSseResponse(lines: string[]): { ok: true; body: ReadableStream<Uint8Array> } {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(line));
      controller.close();
    },
  });
  return { ok: true, body: stream };
}

describe('usePolicyMinesweeper', () => {
  beforeEach(() => {
    generateStream.mockReset();
  });

  it('done 事件驱动 idle → generating → done，并填充 report/reportId', async () => {
    generateStream.mockResolvedValueOnce(
      makeSseResponse([
        'data: {"type":"thinking","message":"开始排雷..."}\n\n',
        'data: {"type":"tool_start","agent":"alpha","tool":"search_stock_news","display_name":"搜索新闻"}\n\n',
        'data: {"type":"done","report_id":"600519_202606261200","status":"success","markdown":"# 排雷报告"}\n\n',
      ]),
    );

    const { result } = renderHook(() => usePolicyMinesweeper());
    expect(result.current.status).toBe('idle');

    await act(async () => {
      await result.current.generate('600519', '贵州茅台', 'medium');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.reportId).toBe('600519_202606261200');
    expect(result.current.report?.markdown).toBe('# 排雷报告');
    expect(result.current.report?.horizon).toBe('medium');
    // thinking + tool_start 入进度步骤；done 不入
    expect(result.current.progressSteps).toHaveLength(2);
    expect(result.current.error).toBeNull();
    // horizon 透传到 api 调用
    expect(generateStream).toHaveBeenCalledWith(
      { stock_code: '600519', stock_name: '贵州茅台', horizon: 'medium' },
      { signal: expect.any(AbortSignal) },
    );
  });

  it('error 事件驱动 → error 状态并带消息', async () => {
    generateStream.mockResolvedValueOnce(
      makeSseResponse([
        'data: {"type":"error","message":"综合裁决失败"}\n\n',
      ]),
    );

    const { result } = renderHook(() => usePolicyMinesweeper());

    await act(async () => {
      await result.current.generate('300750', '示例公司');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('综合裁决失败');
    expect(result.current.report).toBeNull();
  });

  it('reset 清空所有状态回 idle', async () => {
    generateStream.mockResolvedValueOnce(
      makeSseResponse([
        'data: {"type":"done","report_id":"600519_x","status":"success","markdown":"# x"}\n\n',
      ]),
    );

    const { result } = renderHook(() => usePolicyMinesweeper());
    await act(async () => {
      await result.current.generate('600519');
    });
    expect(result.current.status).toBe('done');

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.report).toBeNull();
    expect(result.current.reportId).toBeNull();
    expect(result.current.progressSteps).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('流提前结束且无 done/error → error（连接不完整）', async () => {
    generateStream.mockResolvedValueOnce(
      makeSseResponse([
        'data: {"type":"thinking","message":"思考中..."}\n\n',
        // 流关闭，但没有 done/error
      ]),
    );

    const { result } = renderHook(() => usePolicyMinesweeper());

    await act(async () => {
      await result.current.generate('600519');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('未收到完整报告');
  });
});
