import type React from 'react';
import { Card } from '../common';

interface ValueScenariosCardProps {
  data?: {
    industrySpace?: string;
    competitiveEvolution?: string;
    scenarios?: Array<{
      type: 'optimistic' | 'neutral' | 'pessimistic';
      probability: number;
      valueAnchor?: number | string;
      description?: string;
      upsidePct?: number;
      downsidePct?: number;
    }>;
    horizons?: {
      horizon1y?: string;
      horizon3y?: string;
      horizon5y?: string;
    };
    catalysts?: string[];
    risks?: string[];
  };
}

const getScenarioColor = (type: string): { bg: string; text: string; label: string } => {
  switch (type) {
    case 'optimistic':
      return { bg: 'rgba(52, 211, 153, 0.1)', text: 'rgb(52, 211, 153)', label: '乐观' };
    case 'pessimistic':
      return { bg: 'rgba(248, 113, 113, 0.1)', text: 'rgb(248, 113, 113)', label: '悲观' };
    default:
      return { bg: 'rgba(251, 191, 36, 0.1)', text: 'rgb(251, 191, 36)', label: '中性' };
  }
};

export const ValueScenariosCard: React.FC<ValueScenariosCardProps> = ({ data }) => {
  if (!data) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无价值情景数据
        </div>
      </Card>
    );
  }

  const {
    industrySpace,
    competitiveEvolution,
    scenarios = [],
    horizons,
    catalysts = [],
    risks = [],
  } = data;

  return (
    <div className="space-y-4">
      {/* ③ 长期价值与情景 */}
      <Card variant="bordered" padding="md">
        <h3 className="text-base font-semibold mb-3 text-foreground">③ 长期价值与情景</h3>

        {/* 产业空间 */}
        {industrySpace && (
          <div className="mb-4 p-3 bg-secondary/20 rounded-lg">
            <div className="text-xs text-muted-text mb-1">产业长期空间</div>
            <div className="text-sm">{industrySpace}</div>
          </div>
        )}

        {/* 竞争演变 */}
        {competitiveEvolution && (
          <div className="mb-4 p-3 bg-secondary/10 rounded-lg">
            <div className="text-xs text-muted-text mb-1">竞争格局演变</div>
            <div className="text-sm">{competitiveEvolution}</div>
          </div>
        )}

        {/* 三种情景 */}
        {scenarios.length > 0 && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">三种情景概率</div>
            <div className="space-y-2">
              {scenarios.map((scenario, idx) => {
                const colors = getScenarioColor(scenario.type);
                return (
                  <div
                    key={idx}
                    className="p-3 rounded-lg"
                    style={{ backgroundColor: colors.bg }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium" style={{ color: colors.text }}>
                        {colors.label} ({(scenario.probability * 100).toFixed(0)}%)
                      </span>
                      {scenario.valueAnchor && (
                        <span className="text-sm font-bold" style={{ color: colors.text }}>
                          ¥{typeof scenario.valueAnchor === 'number' ? scenario.valueAnchor.toFixed(2) : scenario.valueAnchor}
                        </span>
                      )}
                    </div>
                    {scenario.description && (
                      <div className="text-xs text-muted-text">{scenario.description}</div>
                    )}
                    {scenario.upsidePct !== undefined && (
                      <div className="text-xs text-muted-text mt-1">
                        上涨空间: +{scenario.upsidePct}%
                      </div>
                    )}
                    {scenario.downsidePct !== undefined && (
                      <div className="text-xs text-muted-text">
                        下跌空间: {scenario.downsidePct}%
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 价值锚 */}
        {horizons && (horizons.horizon1y || horizons.horizon3y || horizons.horizon5y) && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">价值锚</div>
            <div className="grid grid-cols-3 gap-2">
              {horizons.horizon1y && (
                <div className="text-center p-2 bg-secondary/20 rounded">
                  <div className="text-xs text-muted-text">1年</div>
                  <div className="text-sm font-medium">{horizons.horizon1y}</div>
                </div>
              )}
              {horizons.horizon3y && (
                <div className="text-center p-2 bg-secondary/20 rounded">
                  <div className="text-xs text-muted-text">3年</div>
                  <div className="text-sm font-medium">{horizons.horizon3y}</div>
                </div>
              )}
              {horizons.horizon5y && (
                <div className="text-center p-2 bg-secondary/20 rounded">
                  <div className="text-xs text-muted-text">5年</div>
                  <div className="text-sm font-medium">{horizons.horizon5y}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 潜在催化 */}
        {catalysts.length > 0 && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">潜在催化</div>
            <div className="space-y-1">
              {catalysts.map((catalyst, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-green-500 flex-shrink-0">•</span>
                  <span className="text-sm">{catalyst}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 主要风险 */}
        {risks.length > 0 && (
          <div>
            <div className="text-xs text-muted-text mb-2">主要风险</div>
            <div className="space-y-1">
              {risks.map((risk, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-red-500 flex-shrink-0">•</span>
                  <span className="text-sm">{risk}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default ValueScenariosCard;
