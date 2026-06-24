import type React from 'react';
import { Badge, Card } from '../common';

interface ValueScenario {
  probability: number;
  valueAnchor: string;
  upsidePct?: number;
  downsidePct?: number;
  key_assumptions?: string[];
  timeframe_years?: number;
}

interface ValueHorizons {
  horizon1y?: string;
  horizon3y?: string;
  horizon5y?: string;
}

interface ValueAnalysis {
  valueHorizons?: ValueHorizons;
  scenarios?: {
    bullCase?: ValueScenario;
    baseCase?: ValueScenario;
    bearCase?: ValueScenario;
  };
  catalysts?: string[];
  risks?: string[];
  valueScore?: number;
}

interface SupplyChainAnalysis {
  chainPosition?: string;
  chainPosition_rationale?: string;
  moatType?: string;
  moatStrength?: string;
  moat_rationale?: string;
  usChinaRisk?: string;
  chokepoint_type?: string;
  overallSupplyChainScore?: number;
  keyInsights?: string[];
  risks?: string[];
}

interface AgentAnalysisData {
  supplyChainAnalysis?: SupplyChainAnalysis;
  valueAnalysis?: ValueAnalysis;
}

interface AgentAnalysisPanelProps {
  data?: AgentAnalysisData;
  compact?: boolean;
}

const chainPositionLabels: Record<string, string> = {
  bottleneck: '卡脖子',
  upstream: '上游',
  midstream: '中游',
  downstream: '下游',
  commodity: '大宗商品',
};

const moatTypeLabels: Record<string, string> = {
  patent: '专利',
  technology: '技术',
  brand: '品牌',
  network: '网络效应',
  switching_cost: '转换成本',
  license: '许可',
  regulatory: '监管',
  multiple: '多重护城河',
};

const riskLabels: Record<string, string> = {
  high: '高风险',
  medium: '中等风险',
  low: '低风险',
  none: '无风险',
};

const getScoreColor = (score: number): string => {
  if (score >= 75) return 'var(--home-price-up)';
  if (score >= 50) return 'var(--home-accent)';
  if (score >= 25) return 'var(--home-price-flat)';
  return 'var(--home-price-down)';
};

const getScenarioColor = (scenario: string): string => {
  if (scenario === 'bullCase') return 'var(--home-price-up)';
  if (scenario === 'bearCase') return 'var(--home-price-down)';
  return 'var(--home-accent)';
};

export const AgentAnalysisPanel: React.FC<AgentAnalysisPanelProps> = ({
  data,
  compact = false,
}) => {
  if (!data || (!data.supplyChainAnalysis && !data.valueAnalysis)) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无深度分析数据
        </div>
      </Card>
    );
  }

  const { supplyChainAnalysis, valueAnalysis } = data;

  if (compact) {
    return (
      <Card variant="bordered" padding="md">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">AI深度分析</span>
          <div className="flex items-center gap-2">
            {supplyChainAnalysis?.overallSupplyChainScore && (
              <Badge variant="success">
                产业链 {supplyChainAnalysis.overallSupplyChainScore}
              </Badge>
            )}
            {valueAnalysis?.valueScore && (
              <Badge variant="info">
                价值 {valueAnalysis.valueScore}
              </Badge>
            )}
          </div>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* 产业链分析 */}
      {supplyChainAnalysis && (
        <Card variant="bordered" padding="md">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium">产业链分析</h4>
            {supplyChainAnalysis.overallSupplyChainScore && (
              <span 
                className="text-lg font-bold font-mono"
                style={{ color: getScoreColor(supplyChainAnalysis.overallSupplyChainScore) }}
              >
                {supplyChainAnalysis.overallSupplyChainScore}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="text-center p-2 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">产业链位置</div>
              <div className="text-sm font-medium">
                {chainPositionLabels[supplyChainAnalysis.chainPosition || ''] || supplyChainAnalysis.chainPosition || '未知'}
              </div>
            </div>
            <div className="text-center p-2 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">护城河类型</div>
              <div className="text-sm font-medium">
                {moatTypeLabels[supplyChainAnalysis.moatType || ''] || supplyChainAnalysis.moatType || '未知'}
              </div>
            </div>
            <div className="text-center p-2 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">护城河强度</div>
              <div className="text-sm font-medium capitalize">
                {supplyChainAnalysis.moatStrength || '未知'}
              </div>
            </div>
            <div className="text-center p-2 bg-secondary/30 rounded-lg">
              <div className="text-xs text-muted-text mb-1">中美链风险</div>
              <div className="text-sm font-medium">
                {riskLabels[supplyChainAnalysis.usChinaRisk || ''] || supplyChainAnalysis.usChinaRisk || '未知'}
              </div>
            </div>
          </div>

          {supplyChainAnalysis.chainPosition_rationale && (
            <div className="text-xs text-muted-text mb-2 p-2 bg-secondary/20 rounded">
              {supplyChainAnalysis.chainPosition_rationale}
            </div>
          )}

          {supplyChainAnalysis.keyInsights && supplyChainAnalysis.keyInsights.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-muted-text mb-1">关键洞察</div>
              <div className="space-y-1">
                {supplyChainAnalysis.keyInsights.slice(0, 3).map((insight, i) => (
                  <div key={i} className="text-xs flex items-start gap-1">
                    <span className="text-success">•</span>
                    <span>{insight}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* 价值情景分析 */}
      {valueAnalysis && (
        <Card variant="bordered" padding="md">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium">价值情景分析</h4>
            {valueAnalysis.valueScore && (
              <span 
                className="text-lg font-bold font-mono"
                style={{ color: getScoreColor(valueAnalysis.valueScore) }}
              >
                {valueAnalysis.valueScore}
              </span>
            )}
          </div>

          {/* 价值区间 */}
          {valueAnalysis.valueHorizons && (
            <div className="mb-4">
              <div className="text-xs text-muted-text mb-2">价值区间</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center p-2 bg-secondary/30 rounded">
                  <div className="text-xs text-muted-text">1年</div>
                  <div className="text-sm font-medium">{valueAnalysis.valueHorizons.horizon1y || '-'}</div>
                </div>
                <div className="text-center p-2 bg-secondary/30 rounded">
                  <div className="text-xs text-muted-text">3年</div>
                  <div className="text-sm font-medium">{valueAnalysis.valueHorizons.horizon3y || '-'}</div>
                </div>
                <div className="text-center p-2 bg-secondary/30 rounded">
                  <div className="text-xs text-muted-text">5年</div>
                  <div className="text-sm font-medium">{valueAnalysis.valueHorizons.horizon5y || '-'}</div>
                </div>
              </div>
            </div>
          )}

          {/* 情景分析 */}
          {valueAnalysis.scenarios && (
            <div className="space-y-2">
              <div className="text-xs text-muted-text mb-2">情景分析</div>
              
              {valueAnalysis.scenarios.bullCase && (
                <div 
                  className="p-2 rounded-lg border"
                  style={{ borderColor: `${getScenarioColor('bullCase')}40`, backgroundColor: `${getScenarioColor('bullCase')}10` }}
                >
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-medium" style={{ color: getScenarioColor('bullCase') }}>
                      乐观情景
                    </span>
                    <Badge variant="success" className="text-xs">
                      {(valueAnalysis.scenarios.bullCase.probability * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <div className="text-sm">
                    目标价: {valueAnalysis.scenarios.bullCase.valueAnchor || '-'}
                    {valueAnalysis.scenarios.bullCase.upsidePct && (
                      <span className="text-xs ml-2">(+{valueAnalysis.scenarios.bullCase.upsidePct}%)</span>
                    )}
                  </div>
                </div>
              )}

              {valueAnalysis.scenarios.baseCase && (
                <div 
                  className="p-2 rounded-lg border"
                  style={{ borderColor: `${getScenarioColor('baseCase')}40`, backgroundColor: `${getScenarioColor('baseCase')}10` }}
                >
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-medium" style={{ color: getScenarioColor('baseCase') }}>
                      基准情景
                    </span>
                    <Badge variant="info" className="text-xs">
                      {(valueAnalysis.scenarios.baseCase.probability * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <div className="text-sm">
                    目标价: {valueAnalysis.scenarios.baseCase.valueAnchor || '-'}
                    {valueAnalysis.scenarios.baseCase.upsidePct && (
                      <span className="text-xs ml-2">(+{valueAnalysis.scenarios.baseCase.upsidePct}%)</span>
                    )}
                  </div>
                </div>
              )}

              {valueAnalysis.scenarios.bearCase && (
                <div 
                  className="p-2 rounded-lg border"
                  style={{ borderColor: `${getScenarioColor('bearCase')}40`, backgroundColor: `${getScenarioColor('bearCase')}10` }}
                >
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-medium" style={{ color: getScenarioColor('bearCase') }}>
                      悲观情景
                    </span>
                    <Badge variant="danger" className="text-xs">
                      {(valueAnalysis.scenarios.bearCase.probability * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <div className="text-sm">
                    目标价: {valueAnalysis.scenarios.bearCase.valueAnchor || '-'}
                    {valueAnalysis.scenarios.bearCase.downsidePct && (
                      <span className="text-xs ml-2">(-{valueAnalysis.scenarios.bearCase.downsidePct}%)</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 催化剂 */}
          {valueAnalysis.catalysts && valueAnalysis.catalysts.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-muted-text mb-1">催化剂</div>
              <div className="space-y-1">
                {valueAnalysis.catalysts.slice(0, 3).map((catalyst, i) => (
                  <div key={i} className="text-xs flex items-start gap-1">
                    <span className="text-success">+</span>
                    <span>{catalyst}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 风险 */}
          {valueAnalysis.risks && valueAnalysis.risks.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-muted-text mb-1">风险</div>
              <div className="space-y-1">
                {valueAnalysis.risks.slice(0, 3).map((risk, i) => (
                  <div key={i} className="text-xs flex items-start gap-1">
                    <span className="text-danger">!</span>
                    <span>{risk}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default AgentAnalysisPanel;
