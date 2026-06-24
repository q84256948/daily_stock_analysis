import React from 'react';
import { Card, Badge } from '../common';

interface IndicatorDetail {
  name: string;
  score: number;
  weight: number;
  basis: string;
  confidence?: string;
  summary?: string;
}

interface DimensionDetail {
  dimension: string;
  weight: number;
  score: number;
  indicators?: IndicatorDetail[];
  warnings?: string[];
}

interface DimensionDetailPanelProps {
  dimensions?: DimensionDetail[];
  showIndicators?: boolean;
}

const dimensionLabels: Record<string, { zh: string; en: string }> = {
  '产业链定位': { zh: '产业链定位', en: 'Supply Chain' },
  '基本面与价值': { zh: '基本面与价值', en: 'Fundamentals' },
  '资金面': { zh: '资金面', en: 'Capital Flow' },
  '技术面': { zh: '技术面', en: 'Technical' },
  '情绪与认知差': { zh: '情绪与认知差', en: 'Sentiment' },
  '宏观与地缘': { zh: '宏观与地缘', en: 'Macro' },
};

const basisLabels: Record<string, { label: string; color: string }> = {
  'rule': { label: '规则', color: 'var(--home-accent)' },
  'llm': { label: 'LLM', color: 'var(--home-price-up)' },
};

const getScoreColor = (score: number): string => {
  if (score >= 75) return 'var(--home-price-up)';
  if (score >= 50) return 'var(--home-accent)';
  if (score >= 25) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

export const DimensionDetailPanel: React.FC<DimensionDetailPanelProps> = ({
  dimensions = [],
  showIndicators = true,
}) => {
  if (dimensions.length === 0) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无六维详情数据
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card variant="bordered" padding="md">
        <h3 className="text-base font-semibold mb-4 text-foreground">⑤ 六维详情</h3>
        
        <div className="space-y-6">
          {dimensions.map((dim) => {
            const label = dimensionLabels[dim.dimension] || { zh: dim.dimension, en: dim.dimension };
            const hasIndicators = dim.indicators && dim.indicators.length > 0;
            
            return (
              <div key={dim.dimension} className="border-b border-secondary/30 pb-4 last:border-0 last:pb-0">
                {/* 维度标题 */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{label.zh}</span>
                    <Badge variant="default" className="text-xs">
                      权重 {(dim.weight * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <div 
                    className="text-xl font-bold font-mono"
                    style={{ color: getScoreColor(dim.score) }}
                  >
                    {dim.score.toFixed(1)}
                  </div>
                </div>

                {/* 维度进度条 */}
                <div className="h-2 bg-secondary rounded-full overflow-hidden mb-4">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${dim.score}%`,
                      backgroundColor: getScoreColor(dim.score),
                    }}
                  />
                </div>

                {/* 预警信息 */}
                {dim.warnings && dim.warnings.length > 0 && (
                  <div className="mb-3 p-2 bg-warning/10 border border-warning/30 rounded">
                    <div className="text-xs text-warning">
                      {dim.warnings.map((w, i) => (
                        <span key={i}>⚠ {w} </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 指标详情 */}
                {showIndicators && hasIndicators && (
                  <div className="space-y-2">
                    <div className="text-xs text-muted-text">细分指标</div>
                    {dim.indicators!.map((ind, idx) => {
                      const basis = basisLabels[ind.basis] || { label: ind.basis, color: 'var(--text-muted)' };
                      return (
                        <div
                          key={idx}
                          className="p-3 bg-secondary/20 rounded-lg"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium">{ind.name}</span>
                                <Badge
                                  variant="default"
                                  style={{ color: basis.color }}
                                  className="text-xs"
                                >
                                  {basis.label}
                                </Badge>
                                {ind.confidence && (
                                  <span className="text-xs text-muted-text">
                                    ({ind.confidence}可信度)
                                  </span>
                                )}
                              </div>
                              {ind.summary && (
                                <div className="text-xs text-muted-text mt-1">
                                  {ind.summary}
                                </div>
                              )}
                            </div>
                            <div 
                              className="text-sm font-mono font-bold"
                              style={{ color: getScoreColor(ind.score) }}
                            >
                              {ind.score.toFixed(1)}
                            </div>
                          </div>
                          {/* 指标权重 */}
                          <div className="mt-2 flex items-center gap-2 text-xs text-muted-text">
                            <span>权重: {(ind.weight * 100).toFixed(0)}%</span>
                            <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${ind.score}%`,
                                  backgroundColor: getScoreColor(ind.score),
                                }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
};

export default DimensionDetailPanel;
