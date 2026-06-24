import type React from 'react';
import type { ReportLanguage } from '../../types/analysis';
import { Badge, Card } from '../common';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface DimensionScore {
  dimension: string;
  weight: number;
  score: number;
  indicators?: Array<{
    name: string;
    score: number;
    weight: number;
    basis: string;
    summary?: string;
  }>;
}

interface BayesianResult {
  priorP: number;
  marketImpliedP: number;
  edge: number;
  posteriorP: number;
  positionSuggestion: string;
  stopConditions?: {
    shouldStop?: boolean;
    posteriorBelowPriorThreshold?: boolean;
    strongNegativeEvidence?: boolean;
    edgeDisappeared?: boolean;
  };
}

interface ResearchFrameworkData {
  dimensionTotal: number;
  dimensions: DimensionScore[];
  version: string;
  bayesianResult?: BayesianResult;
}

interface ResearchFrameworkPanelProps {
  data?: ResearchFrameworkData;
  compact?: boolean;
  language?: ReportLanguage;
}

const dimensionLabels: Record<string, { zh: string; en: string }> = {
  '产业链定位': { zh: '产业链定位', en: 'Supply Chain' },
  '基本面与价值': { zh: '基本面与价值', en: 'Fundamentals' },
  '资金面': { zh: '资金面', en: 'Capital Flow' },
  '技术面': { zh: '技术面', en: 'Technical' },
  '情绪与认知差': { zh: '情绪与认知差', en: 'Sentiment' },
  '宏观与地缘': { zh: '宏观与地缘', en: 'Macro' },
};

const getScoreColor = (score: number): string => {
  if (score >= 75) return 'var(--home-price-up)';
  if (score >= 50) return 'var(--home-accent)';
  if (score >= 25) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

const getEdgeColor = (edge: number): string => {
  if (edge > 0.2) return 'var(--home-price-up)';
  if (edge > 0) return 'var(--home-accent)';
  if (edge > -0.2) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

const formatProbability = (p: number): string => {
  return `${(p * 100).toFixed(1)}%`;
};

export const ResearchFrameworkPanel: React.FC<ResearchFrameworkPanelProps> = ({
  data,
  compact = false,
  language,
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);

  if (!data) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无投研框架数据
        </div>
      </Card>
    );
  }

  const { dimensionTotal, dimensions, bayesianResult } = data;

  if (compact) {
    return (
      <Card variant="bordered" padding="md">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">六维总分</span>
          <div className="flex items-center gap-3">
            <span 
              className="text-lg font-bold font-mono"
              style={{ color: getScoreColor(dimensionTotal) }}
            >
              {dimensionTotal.toFixed(1)}
            </span>
            {bayesianResult && (
              <Badge 
                variant={bayesianResult.edge > 0 ? 'success' : 'danger'}
              >
                {text.edge} {(bayesianResult.edge * 100).toFixed(1)}%
              </Badge>
            )}
          </div>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* 总分概览 */}
      <Card variant="gradient" padding="md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-foreground">长线投研框架</h3>
          <span 
            className="text-2xl font-bold font-mono"
            style={{ color: getScoreColor(dimensionTotal) }}
          >
            {dimensionTotal.toFixed(1)}
          </span>
        </div>
        
        <div className="h-2 bg-secondary rounded-full overflow-hidden">
          <div 
            className="h-full rounded-full transition-all duration-500"
            style={{ 
              width: `${dimensionTotal}%`,
              backgroundColor: getScoreColor(dimensionTotal),
            }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-text mt-1">
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </div>
      </Card>

      {/* 六维评分 */}
      <Card variant="bordered" padding="md">
        <h4 className="text-sm font-medium mb-3 text-foreground">六维评分</h4>
        <div className="space-y-3">
          {dimensions.map((dim) => {
            const label = dimensionLabels[dim.dimension] || { zh: dim.dimension, en: dim.dimension };
            return (
              <div key={dim.dimension} className="space-y-1">
                <div className="flex justify-between items-center">
                  <span className="text-sm">{label.zh}</span>
                  <div className="flex items-center gap-2">
                    <span 
                      className="text-sm font-mono font-medium"
                      style={{ color: getScoreColor(dim.score) }}
                    >
                      {dim.score.toFixed(1)}
                    </span>
                    <span className="text-xs text-muted-text">
                      ({(dim.weight * 100).toFixed(0)}%)
                    </span>
                  </div>
                </div>
                <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div 
                    className="h-full rounded-full"
                    style={{ 
                      width: `${dim.score}%`,
                      backgroundColor: getScoreColor(dim.score),
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* 贝叶斯分析 */}
      {bayesianResult && (
        <Card variant="bordered" padding="md">
          <h4 className="text-sm font-medium mb-3 text-foreground">贝叶斯分析</h4>
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center p-3 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">{text.priorPH}</div>
              <div className="text-lg font-bold font-mono">
                {formatProbability(bayesianResult.priorP)}
              </div>
            </div>
            <div className="text-center p-3 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">后验概率</div>
              <div className="text-lg font-bold font-mono">
                {formatProbability(bayesianResult.posteriorP)}
              </div>
            </div>
            <div className="text-center p-3 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">市场隐含</div>
              <div className="text-lg font-bold font-mono">
                {formatProbability(bayesianResult.marketImpliedP)}
              </div>
            </div>
            <div className="text-center p-3 rounded-lg" style={{ backgroundColor: `${getEdgeColor(bayesianResult.edge)}20` }}>
              <div className="text-xs mb-1" style={{ color: getEdgeColor(bayesianResult.edge) }}>{text.edge}</div>
              <div 
                className="text-lg font-bold font-mono"
                style={{ color: getEdgeColor(bayesianResult.edge) }}
              >
                {bayesianResult.edge > 0 ? '+' : ''}{(bayesianResult.edge * 100).toFixed(1)}%
              </div>
            </div>
          </div>
          
          {/* 仓位建议 */}
          <div className="mt-4 p-3 bg-secondary/30 rounded-lg text-center">
            <div className="text-xs text-muted-text mb-1">建议仓位</div>
            <div className="text-xl font-bold" style={{ color: getEdgeColor(bayesianResult.edge) }}>
              {bayesianResult.positionSuggestion}
            </div>
          </div>

          {/* 停止条件 */}
          {bayesianResult.stopConditions?.shouldStop && (
            <div className="mt-3 p-2 bg-danger/10 border border-danger/30 rounded text-center">
              <Badge variant="danger" className="text-xs">
                触发止损条件
              </Badge>
              <div className="text-xs text-muted-text mt-1">
                {bayesianResult.stopConditions.posteriorBelowPriorThreshold && '后验低于先验'}
                {bayesianResult.stopConditions.strongNegativeEvidence && '强负向证据'}
                {bayesianResult.stopConditions.edgeDisappeared && `${text.edge}消失`}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default ResearchFrameworkPanel;
