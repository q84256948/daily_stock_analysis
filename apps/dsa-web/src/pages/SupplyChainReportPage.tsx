import { useCallback, useEffect, useState } from 'react';
import {
  Network,
  Download,
  Copy,
  RefreshCw,
  Trash2,
  AlertTriangle,
  X,
  ChevronDown,
  Plus,
  Loader2,
} from 'lucide-react';
import { ReportMarkdownBody } from '../components/report/ReportMarkdownBody';
import { useSupplyChainReport } from '../hooks/useSupplyChainReport';
import {
  supplyChainReportApi,
  type SupplyChainReportItem,
  type SupplyChainReportDetail,
} from '../api/supplyChainReports';
import { cn } from '../utils/cn';

// 主题快捷模板（仅填充「分析主题」，不改变后端契约）
const TOPIC_TEMPLATES: readonly string[] = [
  'A 股 AI 半导体供应链',
  '光模块产业链瓶颈在哪',
  '中际旭创是不是 CPO 核心卡点',
];

/**
 * 供应链分析表单式报告页面（输入分析主题 [+可选线索] → SSE 生成 → 报告展示 + PDF + 历史）。
 *
 * 布局参考 DeepResearchPage 双栏：左栏历史报告列表（desktop w-64 / mobile Drawer），
 * 右栏表单 + 报告/进度/错误。主输入是「分析主题」（非单股票），
 * 「供应链线索」为一次性调查目标（发送后清空、不回填历史线索）。
 */
export function SupplyChainReportPage() {
  const [topic, setTopic] = useState('');
  const [researchHint, setResearchHint] = useState('');
  const [inputError, setInputError] = useState<string | null>(null);
  const [history, setHistory] = useState<SupplyChainReportItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [currentDetail, setCurrentDetail] = useState<SupplyChainReportDetail | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { status, progressSteps, report, reportId, error, generate, cancel, reset } =
    useSupplyChainReport();

  const isGenerating = status === 'generating';

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const items = await supplyChainReportApi.getReports(50);
      setHistory(items);
    } catch {
      // 历史加载失败不阻塞主流程
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // 生成完成后刷新历史列表
  useEffect(() => {
    if (status === 'done' && reportId) {
      loadHistory();
    }
  }, [status, reportId, loadHistory]);

  const handleSubmit = useCallback(() => {
    if (!topic.trim()) {
      setInputError('请输入分析主题');
      return;
    }
    setInputError(null);
    setCurrentDetail(null);
    reset();
    // 线索只随本次请求发送，trim 后为空则不传；发送后清空、保留主题
    const hint = researchHint.trim() || undefined;
    void generate(topic.trim(), hint);
    setResearchHint('');
  }, [topic, researchHint, generate, reset]);

  const handleSelectHistory = useCallback(
    async (id: string) => {
      try {
        const detail = await supplyChainReportApi.getReport(id);
        setCurrentDetail(detail);
        reset();
        setSidebarOpen(false);
        // 不回填 researchHint（线索是一次性调查目标）
      } catch {
        // ignore
      }
    },
    [reset],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await supplyChainReportApi.deleteReport(id);
        await loadHistory();
        if (currentDetail?.id === id) {
          setCurrentDetail(null);
        }
      } catch {
        // ignore
      }
    },
    [loadHistory, currentDetail],
  );

  const handleDownloadPdf = useCallback(async (id: string) => {
    setPdfLoading(true);
    try {
      await supplyChainReportApi.downloadPdf(id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'PDF 下载失败';
      window.alert(msg);
    } finally {
      setPdfLoading(false);
    }
  }, []);

  const handleCopy = useCallback((markdown: string) => {
    void navigator.clipboard.writeText(markdown);
  }, []);

  // 展示的报告：生成结果优先，否则历史选中
  const displayReport = report || currentDetail;
  const displayId = displayReport?.id;
  const showReport =
    !!displayReport && !!displayReport.markdown && !isGenerating && status !== 'error';

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/5 bg-white/2 p-3.5">
        <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan">
          历史报告
        </h2>
        <button
          onClick={loadHistory}
          className="text-muted-text transition-colors hover:text-secondary-text"
          aria-label="刷新"
        >
          <RefreshCw className={cn('h-4 w-4', historyLoading && 'animate-spin')} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {historyLoading && history.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-text">加载中...</div>
        )}
        {!historyLoading && history.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-text">暂无历史报告</div>
        )}
        {history.map((item) => (
          <button
            key={item.id}
            onClick={() => handleSelectHistory(item.id)}
            className={cn(
              'group mb-1 flex w-full items-start justify-between rounded-lg p-2.5 text-left transition-colors hover:bg-white/5',
              currentDetail?.id === item.id && 'bg-white/8',
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-foreground">{item.topic}</div>
              <div className="mt-0.5 truncate text-xs text-muted-text">
                {item.created_at?.slice(0, 16).replace('T', ' ')}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                {item.status === 'partial' && (
                  <span className="inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                    不完整
                  </span>
                )}
                {item.status === 'failed' && (
                  <span className="inline-block rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] text-red-400">
                    失败
                  </span>
                )}
                {item.research_hint && (
                  <span className="inline-block rounded bg-cyan/15 px-1.5 py-0.5 text-[10px] text-cyan">
                    带线索
                  </span>
                )}
                {item.has_pdf && (
                  <span className="inline-block rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-muted-text">
                    PDF
                  </span>
                )}
              </div>
            </div>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                void handleDelete(item.id);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.stopPropagation();
                  void handleDelete(item.id);
                }
              }}
              className="ml-2 flex-shrink-0 rounded p-1 text-muted-text opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
              aria-label="删除"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-5rem)] w-full min-w-0 gap-4 overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
      {/* 左栏：desktop 历史列表 */}
      <div className="hidden h-full w-64 flex-shrink-0 flex-col overflow-hidden rounded-[1.25rem] border border-white/8 bg-card/82 shadow-soft-card md:flex">
        {sidebarContent}
      </div>

      {/* 左栏：mobile Drawer */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <div
            className="absolute bottom-0 left-0 top-0 flex w-72 flex-col overflow-hidden border-r border-white/10 bg-card/95 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}

      {/* 右栏：主区 */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="mb-4 flex-shrink-0 space-y-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-lg border border-white/10 p-1.5 text-muted-text hover:text-secondary-text md:hidden"
              aria-label="历史报告"
            >
              <ChevronDown className="h-4 w-4 rotate-90" />
            </button>
            <Network className="h-6 w-6 text-cyan" />
            <h1 className="text-2xl font-bold text-foreground">供应链分析报告</h1>
          </div>
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-text">快捷主题：</span>
              {TOPIC_TEMPLATES.map((tpl) => (
                <button
                  key={tpl}
                  type="button"
                  disabled={isGenerating}
                  onClick={() => {
                    setTopic(tpl);
                    setInputError(null);
                  }}
                  className="rounded-full border border-white/10 px-3 py-1 text-xs text-secondary-text transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {tpl}
                </button>
              ))}
            </div>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="分析主题（如：A 股 AI 半导体供应链 / 光模块产业链瓶颈 / 中际旭创是不是 CPO 核心卡点）"
              disabled={isGenerating}
              rows={2}
              className="w-full resize-none rounded-xl border border-white/10 bg-white/2 p-3 text-sm text-foreground placeholder:text-muted-text/60 focus:border-cyan/50 focus:outline-none disabled:opacity-60"
            />
            <textarea
              value={researchHint}
              onChange={(e) => setResearchHint(e.target.value)}
              placeholder="增加供应链线索（可选，一次性：客户 / 供应商 / 订单 / 技术路线 / 产能 / 政策关键词）"
              disabled={isGenerating}
              rows={2}
              className="w-full resize-none rounded-xl border border-white/10 bg-white/2 p-3 text-sm text-foreground placeholder:text-muted-text/60 focus:border-cyan/50 focus:outline-none disabled:opacity-60"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleSubmit}
                disabled={isGenerating}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-cyan px-5 text-sm font-semibold text-black transition-colors hover:bg-cyan/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                {isGenerating ? '生成中...' : '生成报告'}
              </button>
              {isGenerating && (
                <button
                  onClick={cancel}
                  className="inline-flex h-11 items-center gap-1.5 rounded-xl border border-white/10 px-3 text-sm text-muted-text hover:text-secondary-text"
                >
                  <X className="h-4 w-4" /> 取消
                </button>
              )}
            </div>
            {inputError && <p className="text-sm text-red-400">{inputError}</p>}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto rounded-[1.25rem] border border-white/8 bg-card/82 p-5 shadow-soft-card">
          {/* 生成中 */}
          {isGenerating && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-secondary-text">
                <Loader2 className="h-5 w-5 animate-spin text-cyan" />
                <span>正在执行 Serenity 9 步供应链深度调研，预计 5-15 分钟，请勿关闭页面...</span>
              </div>
              <details className="rounded-lg border border-white/8 bg-white/2 p-3" open>
                <summary className="cursor-pointer text-sm font-medium text-muted-text">
                  调研步骤（{progressSteps.length}）
                </summary>
                <div className="mt-2 max-h-60 space-y-1 overflow-y-auto text-xs text-muted-text">
                  {progressSteps.map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-cyan/60">›</span>
                      <span>
                        {s.type === 'thinking' && s.message}
                        {s.type === 'tool_start' && `调用工具：${s.display_name || s.tool}`}
                        {s.type === 'tool_done' && `完成：${s.display_name || s.tool}`}
                        {s.type === 'generating' && s.message}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            </div>
          )}

          {/* 错误 */}
          {status === 'error' && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <AlertTriangle className="h-10 w-10 text-amber-400" />
              <p className="max-w-md text-secondary-text">{error}</p>
              <button
                onClick={handleSubmit}
                className="inline-flex items-center gap-2 rounded-lg bg-cyan px-4 py-2 text-sm font-semibold text-black hover:bg-cyan/90"
              >
                <RefreshCw className="h-4 w-4" /> 重试
              </button>
            </div>
          )}

          {/* 空状态 */}
          {status === 'idle' && !showReport && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-muted-text">
              <Network className="h-10 w-10 opacity-40" />
              <p>输入分析主题（可选附供应链线索），生成供应链深度调研报告</p>
              <p className="text-xs">Serenity 9 步：产业链层级排序 → 卡点层 → 候选标的 → 证伪条件</p>
            </div>
          )}

          {/* 报告展示 */}
          {showReport && displayReport && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {displayId && (
                  <button
                    onClick={() => handleDownloadPdf(displayId)}
                    disabled={pdfLoading}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-secondary-text hover:bg-white/5 disabled:opacity-60"
                  >
                    {pdfLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                    {pdfLoading ? '生成 PDF...' : '下载 PDF'}
                  </button>
                )}
                <button
                  onClick={() => handleCopy(displayReport.markdown)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-secondary-text hover:bg-white/5"
                >
                  <Copy className="h-4 w-4" /> 复制 Markdown
                </button>
                {report && (
                  <button
                    onClick={handleSubmit}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-secondary-text hover:bg-white/5"
                  >
                    <RefreshCw className="h-4 w-4" /> 重新生成
                  </button>
                )}
                {displayReport.status === 'partial' && (
                  <span className="ml-auto inline-flex items-center gap-1 text-xs text-amber-300">
                    <AlertTriangle className="h-3.5 w-3.5" /> 报告不完整
                  </span>
                )}
              </div>
              <ReportMarkdownBody
                content={displayReport.markdown}
                className="deep-research-prose"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SupplyChainReportPage;
