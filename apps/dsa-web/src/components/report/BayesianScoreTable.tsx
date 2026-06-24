import type React from 'react';
import type { ReportLanguage } from '../../types/analysis';
import { Card } from '../common';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface BayesianScoreTableProps {
  data?: {
    priorP?: number;
    marketImpliedP?: number;
    edge?: number;
    posteriorP?: number;
    positionSuggestion?: string;
    evidenceLog?: Array<{
      evidence: string;
      strength: 'strong_pos' | 'weak_pos' | 'neutral' | 'weak_neg' | 'strong_neg';
      lr: number;
      posteriorP: number;
      date: string;
    }>;
    stopConditions?: {
      shouldStop?: boolean;
      posteriorBelowPriorThreshold?: boolean;
      strongNegativeEvidence?: boolean;
      edgeDisappeared?: boolean;
    };
  };
  language?: ReportLanguage;
}

const getStrengthIcon = (strength: string): { icon: string; color: string } => {
  switch (strength) {
    case 'strong_pos':
      return { icon: '✓✓', color: 'var(--home-price-up)' };
    case 'weak_pos':
      return { icon: '✓', color: 'var(--home-price-up)' };
    case 'strong_neg':
      return { icon: '✗✗', color: 'var(--home-price-down)' };
    case 'weak_neg':
      return { icon: '✗', color: 'var(--home-price-down)' };
    default:
      return { icon: '—', color: 'var(--text-muted)' };
  }
};

const getEdgeColor = (edge?: number): string => {
  if (edge === undefined) return 'var(--text-muted)';
  if (edge > 0.15) return 'var(--home-price-up)';
  if (edge > 0) return 'var(--home-accent)';
  if (edge > -0.15) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

export const BayesianScoreTable: React.FC<BayesianScoreTableProps> = ({ data, language }) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);

  if (!data) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无贝叶斯评分数据
        </div>
      </Card>
    );
  }

  const {
    priorP,
    marketImpliedP,
    edge,
    posteriorP,
    positionSuggestion,
    evidenceLog = [],
    stopConditions,
  } = data;

  const hasEvidence = evidenceLog.length > 0;
  const shouldStop = stopConditions?.shouldStop;

  return (
    <div className="space-y-4">
      {/* ④ 贝叶斯评分表 */}
      <Card variant="bordered" padding="md">
        <h3 className="text-base font-semibold mb-3 text-foreground">④ 贝叶斯评分表</h3>

        {/* 核心概率指标 */}
        <div className="mb-4">
          <div className="grid grid-cols-4 gap-2">
            <div className="text-center p-3 bg-secondary/20 rounded-lg">
              <div className="text-xs text-muted-text mb-1">{text.priorPH}</div>
              <div className="text-lg font-bold font-mono">
                {priorP !== undefined ? `${(priorP * 100).toFixed(1)}%` : '-'}
              </div>
            </div>
            <div className="text-center p-3 bg-secondary/20 rounded-lg">
              <div className="text-xs text-muted-text mb-1">市场隐含</div>
              <div className="text-lg font-bold font-mono">
                {marketImpliedP !== undefined ? `${(marketImpliedP * 100).toFixed(1)}%` : '-'}
              </div>
            </div>
            <div className="text-center p-3 bg-secondary/20 rounded-lg">
              <div className="text-xs text-muted-text mb-1">{text.edge}</div>
              <div
                className="text-lg font-bold font-mono"
                style={{ color: getEdgeColor(edge) }}
              >
                {edge !== undefined
                  ? `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`
                  : '-'}
              </div>
            </div>
            <div className="text-center p-3 bg-secondary/20 rounded-lg">
              <div className="text-xs text-muted-text mb-1">后验 P(H)</div>
              <div className="text-lg font-bold font-mono">
                {posteriorP !== undefined ? `${(posteriorP * 100).toFixed(1)}%` : '-'}
              </div>
            </div>
          </div>
        </div>

        {/* 公式说明 */}
        <div className="mb-4 p-2 bg-primary/10 rounded text-xs text-center">
          <span className="text-muted-text">
            P(H|E) = P(E|H) × P(H) / P(E) &nbsp;|&nbsp;
            Edge = P(H) − 市场隐含概率
          </span>
        </div>

        {/* 证据序列 */}
        {hasEvidence && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">证据序列</div>
            <div className="space-y-2">
              {evidenceLog.map((evidence, idx) => {
                const { icon, color } = getStrengthIcon(evidence.strength);
                const isPositive = evidence.strength.includes('pos');
                return (
                  <div
                    key={idx}
                    className="flex items-center gap-2 p-2 bg-secondary/20 rounded text-sm"
                  >
                    <span className="font-bold" style={{ color }}>{icon}</span>
                    <span className="flex-1 truncate">{evidence.evidence}</span>
                    <span className="text-xs text-muted-text">
                      LR={evidence.lr.toFixed(1)}
                    </span>
                    <span
                      className="text-xs font-mono"
                      style={{ color: isPositive ? 'var(--home-price-up)' : 'var(--home-price-down)' }}
                    >
                      {isPositive ? '+' : ''}
                      {((evidence.posteriorP - (priorP || 0)) * 100).toFixed(1)}%
                    </span>
                    <span className="text-xs text-muted-text">{evidence.date}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 仓位建议 */}
        {positionSuggestion && (
          <div className="mb-4 p-3 bg-secondary/30 rounded-lg text-center">
            <div className="text-xs text-muted-text mb-1">建议仓位</div>
            <div
              className="text-xl font-bold"
              style={{ color: getEdgeColor(edge) }}
            >
              {positionSuggestion}
            </div>
          </div>
        )}

        {/* 止损条件 */}
        {shouldStop && stopConditions && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-red-500 font-bold">⚠ 触发止损条件</span>
            </div>
            <div className="text-sm space-y-1">
              {stopConditions.posteriorBelowPriorThreshold && (
                <div className="text-red-400">• 后验低于先验×60%阈值</div>
              )}
              {stopConditions.strongNegativeEvidence && (
                <div className="text-red-400">• 存在强反面证据</div>
              )}
              {stopConditions.edgeDisappeared && (
                <div className="text-red-400">• Edge 消失</div>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default BayesianScoreTable;
