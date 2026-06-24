import type React from 'react';
import type { ReportLanguage } from '../../types/analysis';
import { Card } from '../common';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface InvestmentConclusionProps {
  data?: {
    action?: '建仓' | '加仓' | '持有' | '减仓' | '止损' | '观察';
    position?: string;
    priorP?: number;
    marketImpliedP?: number;
    edge?: number;
    posteriorP?: number;
    chainPositionSummary?: string;
    valueRange1y?: string;
    valueRange3y?: string;
    valueRange5y?: string;
    rationale?: string;
  };
  language?: ReportLanguage;
}

const getActionColor = (action?: string): string => {
  switch (action) {
    case '建仓':
    case '加仓':
      return 'var(--home-price-up)';
    case '持有':
      return 'var(--home-accent)';
    case '减仓':
    case '止损':
      return 'var(--home-price-down)';
    default:
      return 'var(--text-muted)';
  }
};

const getEdgeColor = (edge?: number): string => {
  if (edge === undefined) return 'var(--text-muted)';
  if (edge > 0.15) return 'var(--home-price-up)';
  if (edge > 0) return 'var(--home-accent)';
  if (edge > -0.15) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

export const InvestmentConclusionCard: React.FC<InvestmentConclusionProps> = ({ data, language }) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);

  if (!data) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无投资结论数据
        </div>
      </Card>
    );
  }

  const {
    action = '观察',
    position = '观察',
    priorP,
    edge,
    posteriorP,
    marketImpliedP,
    chainPositionSummary,
    valueRange1y,
    valueRange3y,
    valueRange5y,
    rationale,
  } = data;

  const formatPct = (v?: number) => v !== undefined ? `${(v * 100).toFixed(0)}%` : '-';
  const formatEdgeDisplay = () => {
    if (edge === undefined) return '-';
    const aiView = posteriorP ?? priorP;
    const market = marketImpliedP;
    return `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(0)}%（AI：${formatPct(aiView)}，市场：${formatPct(market)}）`;
  };

  return (
    <div className="space-y-4">
      {/* ① 投资结论 */}
      <Card variant="gradient" padding="md">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-foreground">① 投资结论</h3>
          <span
            className="px-3 py-1 rounded-full text-sm font-medium"
            style={{
              backgroundColor: `${getActionColor(action)}20`,
              color: getActionColor(action),
            }}
          >
            {action}
          </span>
        </div>

        {/* P(H) + AI观点 + 优势 展示 */}
        <div className="grid grid-cols-3 gap-3 mb-4 p-3 bg-secondary/30 rounded-lg">
          <div className="text-center">
            <div className="text-xs text-muted-text mb-1">{text.priorPH}</div>
            <div className="text-lg font-bold font-mono">
              {formatPct(priorP)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-text mb-1">{text.aiPerspective}</div>
            <div className="text-lg font-bold font-mono">
              {formatPct(posteriorP ?? priorP)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-text mb-1">{text.edge}</div>
            <div
              className="text-sm font-bold font-mono"
              style={{ color: getEdgeColor(edge) }}
            >
              {formatEdgeDisplay()}
            </div>
          </div>
        </div>

        {/* 长线仓位 */}
        <div className="mb-3 p-2 bg-primary/10 rounded">
          <div className="text-xs text-muted-text mb-1">{text.longTermPosition}</div>
          <div className="text-sm font-medium">{position}</div>
        </div>

        {/* 产业链定位 */}
        {chainPositionSummary && (
          <div className="mb-3 p-2 bg-primary/10 rounded">
            <div className="text-xs text-muted-text mb-1">产业链定位</div>
            <div className="text-sm">{chainPositionSummary}</div>
          </div>
        )}

        {/* 价值区间 */}
        {(valueRange1y || valueRange3y || valueRange5y) && (
          <div className="mb-3">
            <div className="text-xs text-muted-text mb-2">价值区间</div>
            <div className="grid grid-cols-3 gap-2">
              <div className="text-center p-2 bg-secondary/20 rounded">
                <div className="text-xs text-muted-text">1年</div>
                <div className="text-sm font-medium">{valueRange1y || '-'}</div>
              </div>
              <div className="text-center p-2 bg-secondary/20 rounded">
                <div className="text-xs text-muted-text">3年</div>
                <div className="text-sm font-medium">{valueRange3y || '-'}</div>
              </div>
              <div className="text-center p-2 bg-secondary/20 rounded">
                <div className="text-xs text-muted-text">5年</div>
                <div className="text-sm font-medium">{valueRange5y || '-'}</div>
              </div>
            </div>
          </div>
        )}

        {/* 投资理由 */}
        {rationale && (
          <div className="mt-3 p-3 bg-secondary/20 rounded">
            <div className="text-xs text-muted-text mb-1">投资理由</div>
            <div className="text-sm">{rationale}</div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default InvestmentConclusionCard;
