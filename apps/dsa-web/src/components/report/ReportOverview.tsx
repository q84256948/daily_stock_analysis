import type React from 'react';
import type {
  ReportDetails as ReportDetailsType,
  ReportMeta,
  ReportSummary as ReportSummaryType,
} from '../../types/analysis';
import { Badge, Card, ScoreGauge } from '../common';
import { formatDateTime } from '../../utils/format';
import { getMarketPhaseSummaryLabel, getPartialBarLabel } from '../../utils/marketPhase';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportOverviewProps {
  meta: ReportMeta;
  summary: ReportSummaryType;
  details?: ReportDetailsType;
  isHistory?: boolean;
  watchlist?: {
    isInWatchlist: (code: string) => boolean;
    onToggle: (code: string) => void;
    isActioning: boolean;
    actionMessage: string | null;
  };
}

type BoardStatus = 'leading' | 'lagging';

type BoardSignal = {
  status: BoardStatus;
  changePct?: number;
};

const normalizeBoardName = (value?: string): string =>
  (value || '').trim().replace(/\s+/g, ' ');

const coerceFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim().replace(/%$/, '');
    if (!trimmed) {
      return undefined;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const buildBoardSignalMap = (details?: ReportDetailsType): Map<string, BoardSignal> => {
  const signalMap = new Map<string, BoardSignal>();
  const topBoards = Array.isArray(details?.sectorRankings?.top) ? details.sectorRankings.top : [];
  const bottomBoards = Array.isArray(details?.sectorRankings?.bottom) ? details.sectorRankings.bottom : [];

  topBoards.forEach((item) => {
    const normalizedName = normalizeBoardName(item?.name);
    if (!normalizedName) return;
    signalMap.set(normalizedName, { status: 'leading', changePct: coerceFiniteNumber(item.changePct) });
  });

  bottomBoards.forEach((item) => {
    const normalizedName = normalizeBoardName(item?.name);
    if (!normalizedName) return;
    signalMap.set(normalizedName, { status: 'lagging', changePct: coerceFiniteNumber(item.changePct) });
  });

  return signalMap;
};

/**
 * 报告概览区组件 - 单卡片布局
 */
export const ReportOverview: React.FC<ReportOverviewProps> = ({
  meta,
  summary,
  details,
}) => {
  const reportLanguage = normalizeReportLanguage(meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const marketPhaseLabel = getMarketPhaseSummaryLabel(meta.marketPhaseSummary, reportLanguage);
  const partialBarLabel = meta.marketPhaseSummary?.isPartialBar === true ? getPartialBarLabel(reportLanguage) : null;
  const relatedBoards = (Array.isArray(details?.belongBoards) ? details.belongBoards : [])
    .filter((board) => normalizeBoardName(board?.name).length > 0);
  const boardSignals = buildBoardSignalMap(details);

  const getPriceChangeStyle = (changePct: number | undefined): React.CSSProperties | undefined => {
    if (changePct === undefined || changePct === null) return undefined;
    if (changePct > 0) return { color: 'var(--home-price-up)' };
    if (changePct < 0) return { color: 'var(--home-price-down)' };
    return undefined;
  };

  const formatChangePct = (changePct: number | undefined): string => {
    if (changePct === undefined || changePct === null) return '--';
    const sign = changePct > 0 ? '+' : '';
    return `${sign}${changePct.toFixed(2)}%`;
  };

  const getBoardStatusVariant = (status: BoardStatus): 'success' | 'danger' => {
    return status === 'leading' ? 'success' : 'danger';
  };

  return (
    <div className="space-y-4">
      {/* 股票头部信息 - 包含操作建议、趋势预测、原因、智能解析和关联板块 */}
      <Card variant="gradient" padding="md" className="home-report-hero">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-2xl font-bold text-foreground">
                {meta.stockName || meta.stockCode}
              </h2>
              {meta.currentPrice != null && (
                <div className="flex items-baseline gap-2">
                  <span className="text-xl font-bold font-mono" style={getPriceChangeStyle(meta.changePct)}>
                    {meta.currentPrice.toFixed(2)}
                  </span>
                  <span className="text-sm font-semibold font-mono" style={getPriceChangeStyle(meta.changePct)}>
                    {formatChangePct(meta.changePct)}
                  </span>
                </div>
              )}
              <span className="home-accent-chip px-2 py-0.5 font-mono text-xs">
                {meta.stockCode}
              </span>
              {marketPhaseLabel && (
                <Badge variant="info" className="gap-1.5 shadow-none">{marketPhaseLabel}</Badge>
              )}
              {partialBarLabel && (
                <Badge variant="warning" className="shadow-none">{partialBarLabel}</Badge>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-text">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              {formatDateTime(meta.createdAt)}
            </div>
          </div>

          {/* 右上角：情绪仪表盘 */}
          <div className="shrink-0">
            <ScoreGauge score={summary.sentimentScore} size="md" language={reportLanguage} />
          </div>
        </div>

        {/* 操作建议和趋势预测 + 原因 */}
        <div className="mt-3 pt-3 border-t border-subtle/50">
          <div className="flex items-center gap-6 mb-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-text uppercase tracking-wide">{text.actionAdvice}</span>
              <Badge
                variant={summary.operationAdvice === '买入' || summary.operationAdvice === '加仓' ? 'success' : summary.operationAdvice === '卖出' || summary.operationAdvice === '减仓' ? 'danger' : 'warning'}
                className="font-bold text-sm"
              >
                {summary.operationAdvice || text.noAdvice}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-text uppercase tracking-wide">{text.trendPrediction}</span>
              <span className="text-sm font-medium">{summary.trendPrediction || text.noPrediction}</span>
            </div>
          </div>
          {summary.actionReason && (
            <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
              {summary.actionReason}
            </p>
          )}
        </div>

        {/* 智能解析 */}
        {summary.analysisSummary && (
          <div className="mt-3 pt-3 border-t border-subtle/50">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-text mb-2">
              <svg className="w-3.5 h-3.5 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              智能解析
            </h3>
            <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
              {summary.analysisSummary}
            </p>
          </div>
        )}

        {/* 关联板块 */}
        {relatedBoards.length > 0 && (
          <div className="mt-3 pt-3 border-t border-subtle/50">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-text mb-2">{text.relatedBoards}</h3>
            <div className="flex flex-wrap gap-2">
              {relatedBoards.map((board, index) => {
                const boardName = normalizeBoardName(board.name);
                const signal = boardSignals.get(boardName);
                return (
                  <div key={`${boardName}-${board.code || index}`} className="inline-flex items-center gap-1.5">
                    <span className="home-accent-chip px-2 py-0.5 text-xs font-medium">{boardName}</span>
                    {board.type && (
                      <span className="home-board-pill rounded-full px-2 py-0.5 text-xs">{board.type}</span>
                    )}
                    {signal && (
                      <>
                        <Badge variant={getBoardStatusVariant(signal.status)} className="shadow-none text-xs">
                          {signal.status === 'leading' ? text.leadingBoard : text.laggingBoard}
                        </Badge>
                        {signal.changePct !== undefined && signal.changePct !== null && (
                          <span className="text-xs font-mono" style={getPriceChangeStyle(signal.changePct)}>
                            {formatChangePct(signal.changePct)}
                          </span>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};
