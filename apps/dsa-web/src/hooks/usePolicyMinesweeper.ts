import { useCallback, useEffect, useRef, useState } from 'react';
import {
  policyMinesweeperApi,
  type PolicyMinesweeperHorizon,
  type PolicyMinesweeperReportDetail,
} from '../api/policyMinesweeper';

export type PolicyMinesweeperStatus = 'idle' | 'generating' | 'done' | 'error';

export interface PolicyMinesweeperProgressStep {
  type: string;
  step?: number;
  message?: string;
  tool?: string;
  display_name?: string;
  /** α/β/Ω 角色标记（由后端 progress 事件携带，前端可分阶段高亮）。 */
  agent?: string;
  success?: boolean;
}

/**
 * 政策与公告双维度排雷生成 hook（表单流：一次性 SSE 生成）。
 *
 * 与 useDeepResearch 同构（fetch + ReadableStream + `data: ` 行解析）：
 * - AbortController：用户可取消（cancel）。
 * - 心跳 watchdog：90s 内无任何事件（含 heartbeat）视为断线 → error。
 * - 状态机：idle → generating → done | error。
 *
 * 差异：generate 多一个 horizon 参数（short/medium/long）。
 * done 事件携带 {report_id, status, markdown, error}；综合分/等级/置信度由
 * 报告正文 Markdown 的 scorecard banner 呈现（详情接口额外提供结构化字段）。
 */
export function usePolicyMinesweeper() {
  const [status, setStatus] = useState<PolicyMinesweeperStatus>('idle');
  const [progressSteps, setProgressSteps] = useState<PolicyMinesweeperProgressStep[]>([]);
  const [report, setReport] = useState<PolicyMinesweeperReportDetail | null>(null);
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
    async (stockCode: string, stockName?: string, horizon: PolicyMinesweeperHorizon = 'medium') => {
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
        const response = await policyMinesweeperApi.generateStream(
          { stock_code: stockCode, stock_name: stockName, horizon },
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

            let event: PolicyMinesweeperProgressStep & {
              report_id?: string;
              markdown?: string;
              status?: string;
              message?: string;
              error?: string;
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
                horizon,
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
