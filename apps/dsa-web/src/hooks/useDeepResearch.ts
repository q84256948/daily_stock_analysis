import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deepResearchApi,
  type DeepResearchReportDetail,
} from '../api/deepResearch';

export type DeepResearchStatus = 'idle' | 'generating' | 'done' | 'error';

export interface DeepResearchProgressStep {
  type: string;
  step?: number;
  message?: string;
  tool?: string;
  display_name?: string;
  success?: boolean;
}

/**
 * 深度投研报告生成 hook（表单流：一次性 SSE 生成）。
 *
 * 参考 agentChatStore 的 SSE 解析（fetch + ReadableStream + `data: ` 行），
 * 增强点：
 * - AbortController：用户可取消（cancel）。
 * - 心跳 watchdog：90s 内无任何事件（含 heartbeat）视为断线 → error。
 * - 状态机：idle → generating → done | error。
 *
 * 注意：断线不做自动重连（一次性生成，重连=重复生成浪费）。断线提示用户
 * 去"历史列表"查看（报告可能已在后端生成落盘）。
 */
export function useDeepResearch() {
  const [status, setStatus] = useState<DeepResearchStatus>('idle');
  const [progressSteps, setProgressSteps] = useState<DeepResearchProgressStep[]>([]);
  const [report, setReport] = useState<DeepResearchReportDetail | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 90s 无事件 = 断线（服务端每 30s 发心跳，90s 容忍 2 次心跳丢失）
  const WATCHDOG_MS = 90_000;

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  }, []);

  const resetWatchdog = useCallback(() => {
    clearWatchdog();
    watchdogRef.current = setTimeout(() => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      setStatus('error');
      setError('连接超时中断。若报告已生成，可在左侧历史列表查看。');
    }, WATCHDOG_MS);
  }, [clearWatchdog]);

  const generate = useCallback(
    async (stockCode: string, stockName?: string) => {
      // 重置状态
      setStatus('generating');
      setProgressSteps([]);
      setReport(null);
      setReportId(null);
      setError(null);

      const ac = new AbortController();
      abortRef.current = ac;
      resetWatchdog();

      try {
        const response = await deepResearchApi.generateStream(
          { stock_code: stockCode, stock_name: stockName, report_type: 'deep' },
          { signal: ac.signal },
        );
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('SSE 流不可用');
        }
        const decoder = new TextDecoder();
        let buf = '';
        let doneReceived = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            // 收到任意事件重置 watchdog（含心跳）
            resetWatchdog();

            let event: DeepResearchProgressStep & {
              report_id?: string;
              markdown?: string;
              status?: string;
              quality_score?: number;
              missing_layers?: string[];
              message?: string;
              error?: string;
              success?: boolean;
            };
            try {
              event = JSON.parse(line.slice(6));
            } catch {
              continue;
            }

            if (event.type === 'done') {
              doneReceived = true;
              const rid = event.report_id ?? null;
              setReportId(rid);
              setReport({
                id: rid ?? '',
                stock_code: stockCode,
                stock_name: stockName || stockCode,
                markdown: event.markdown || '',
                status: event.status,
                quality_score: event.quality_score,
                missing_layers: event.missing_layers || [],
              });
              if (rid) {
                setStatus('done');
              } else {
                setStatus('error');
                setError(event.message || event.error || '报告生成失败');
              }
              break;
            }

            if (event.type === 'error') {
              doneReceived = true;
              setStatus('error');
              setError(event.message || '生成失败，请重试');
              break;
            }

            if (event.type === 'heartbeat') {
              continue; // 心跳仅用于重置 watchdog，不入 steps
            }

            // thinking / tool_start / tool_done / generating → 进度步骤
            setProgressSteps((prev) => [...prev, event]);
          }

          if (doneReceived) break;
        }

        // 流正常结束但没收到 done/error 事件
        if (!doneReceived && !ac.signal.aborted) {
          setStatus('error');
          setError('连接已结束但未收到完整报告，请稍后在历史列表查看或重试。');
        }
      } catch (e: unknown) {
        const err = e as { name?: string; message?: string };
        if (err?.name === 'AbortError') {
          // 用户取消：静默回 idle
          setStatus('idle');
        } else {
          setStatus('error');
          setError(err?.message || '连接失败，请检查网络后重试');
        }
      } finally {
        clearWatchdog();
        abortRef.current = null;
      }
    },
    [resetWatchdog, clearWatchdog],
  );

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    setStatus('idle');
  }, []);

  const reset = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    clearWatchdog();
    setStatus('idle');
    setProgressSteps([]);
    setReport(null);
    setReportId(null);
    setError(null);
  }, [clearWatchdog]);

  // 卸载时清理
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      clearWatchdog();
    };
  }, [clearWatchdog]);

  return { status, progressSteps, report, reportId, error, generate, cancel, reset };
}
