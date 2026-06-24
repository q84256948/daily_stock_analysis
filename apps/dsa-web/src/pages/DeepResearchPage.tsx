import { useCallback, useEffect, useState } from 'react';
import {
  FileText,
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
import { StockAutocomplete } from '../components/StockAutocomplete/StockAutocomplete';
import { ReportMarkdownBody } from '../components/report/ReportMarkdownBody';
import { useDeepResearch } from '../hooks/useDeepResearch';
import {
  deepResearchApi,
  type DeepResearchReportItem,
  type DeepResearchReportDetail,
} from '../api/deepResearch';
import { cn } from '../utils/cn';

interface SelectedStock {
  code: string;
  name?: string;
}

/**
 * A股深度投研报告页面（表单流：输入股票 → SSE 生成 → 报告展示 + PDF + 历史）。
 *
 * 布局参考 SupplyChainChatPage 双栏：左栏历史报告列表（desktop w-64 / mobile Drawer），
 * 右栏表单 + 报告/进度/错误。
 *
 * 交互：StockAutocomplete 选中联想项即记录 selectedStock（不立即生成），
 * 用户点"生成报告"按钮才触发 generate（避免误触）。
 */
export function DeepResearchPage() {
  const [query, setQuery] = useState('');
  const [selectedStock, setSelectedStock] = useState<SelectedStock | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const [history, setHistory] = useState<DeepResearchReportItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [currentDetail, setCurrentDetail] = useState<DeepResearchReportDetail | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { status, progressSteps, report, reportId, error, generate, cancel, reset } =
    useDeepResearch();

  const isGenerating = status === 'generating';

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const items = await deepResearchApi.getReports(50);
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
    if (!selectedStock) {
      setInputError('请先选择一只 A 股');
      return;
    }
    setInputError(null);
    setCurrentDetail(null);
    reset();
    void generate(selectedStock.code, selectedStock.name);
  }, [selectedStock, generate, reset]);

  const handleSelectHistory = useCallback(
    async (id: string) => {
      try {
        const detail = await deepResearchApi.getReport(id);
        setCurrentDetail(detail);
        reset();
        setSidebarOpen(false);
      } catch {
        // ignore
      }
    },
    [reset],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deepResearchApi.deleteReport(id);
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
      await deepResearchApi.downloadPdf(id);
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
          title="刷新"
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
              <div className="truncate text-sm font-medium text-foreground">
                {item.stock_name || item.stock_code}
              </div>
              <div className="mt-0.5 truncate text-xs text-muted-text">
                {item.stock_code} · {item.created_at?.slice(0, 16).replace('T', ' ')}
              </div>
              {item.status === 'partial' && (
                <span className="mt-1 inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                  不完整
                </span>
              )}
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
              title="删除"
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
            <FileText className="h-6 w-6 text-cyan" />
            <h1 className="text-2xl font-bold text-foreground">A股深度投研报告</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-[240px] flex-1">
              <StockAutocomplete
                value={query}
                onChange={setQuery}
                onSubmit={(code, name) => {
                  // 选中联想项或回车：记录选中股票（不立即生成，由按钮触发）
                  setSelectedStock({ code, name });
                  setQuery(name ? `${name} ${code}` : code);
                  setInputError(null);
                }}
                placeholder="输入 A 股代码或名称（如 600519 / 贵州茅台）"
                disabled={isGenerating}
              />
            </div>
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
        </header>

        <div className="flex-1 overflow-y-auto rounded-[1.25rem] border border-white/8 bg-card/82 p-5 shadow-soft-card">
          {/* 生成中 */}
          {isGenerating && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-secondary-text">
                <Loader2 className="h-5 w-5 animate-spin text-cyan" />
                <span>正在执行五层穿透深度分析，预计 2-5 分钟，请勿关闭页面...</span>
              </div>
              <details className="rounded-lg border border-white/8 bg-white/2 p-3" open>
                <summary className="cursor-pointer text-sm font-medium text-muted-text">
                  分析步骤（{progressSteps.length}）
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
              <FileText className="h-10 w-10 opacity-40" />
              <p>输入 A 股代码或名称，生成机构级深度投研报告</p>
              <p className="text-xs">五层穿透：宏观 → 产业 → 财务 → 估值 → 博弈</p>
            </div>
          )}

          {/* 报告展示 */}
          {showReport && displayReport && (
            <div className="space-y-3">
              {displayReport.missing_layers && displayReport.missing_layers.length > 0 && (
                <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                  <span>
                    以下层次分析不充分：{displayReport.missing_layers.join('、')}
                  </span>
                </div>
              )}
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
                {displayReport.quality_score != null && (
                  <span className="ml-auto text-xs text-muted-text">
                    质量评分：{displayReport.quality_score}/100
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

export default DeepResearchPage;
