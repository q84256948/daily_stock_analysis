import type React from 'react';
import type { AnalysisReport, ReportLanguage } from '../../types/analysis';
import { InvestmentConclusionCard } from './InvestmentConclusionCard';
import { SupplyChainPanel } from './SupplyChainPanel';
import { ValueScenariosCard } from './ValueScenariosCard';
import { BayesianScoreTable } from './BayesianScoreTable';
import { ResearchFrameworkPanel } from './ResearchFrameworkPanel';
import { DimensionDetailPanel } from './DimensionDetailPanel';

interface FiveSectionReportViewProps {
  report?: AnalysisReport;
  showCompact?: boolean;
  language?: ReportLanguage;
}

export const FiveSectionReportView: React.FC<FiveSectionReportViewProps> = ({
  report,
  showCompact = false,
  language,
}) => {
  if (!report) {
    return null;
  }

  const {
    investmentConclusion,
    supplyChain,
    valueScenarios,
    bayesianFramework,
    researchFramework,
  } = report;

  const hasAnySection = investmentConclusion || supplyChain || valueScenarios || 
                        bayesianFramework || researchFramework;

  if (!hasAnySection) {
    return null;
  }

  const bayesianData = bayesianFramework || researchFramework?.bayesianResult;

  const frameworkData = researchFramework ? {
    dimensionTotal: researchFramework.dimensionTotal,
    dimensions: researchFramework.dimensions || [],
    version: researchFramework.version || 'v1',
    bayesianResult: bayesianFramework ? {
      priorP: bayesianFramework.priorP,
      marketImpliedP: bayesianFramework.marketImpliedP,
      edge: bayesianFramework.edge,
      posteriorP: bayesianFramework.posteriorP,
      positionSuggestion: bayesianFramework.positionSuggestion,
      stopConditions: bayesianFramework.stopConditions,
    } : undefined,
  } : undefined;

  if (showCompact) {
    return (
      <div className="space-y-3">
        {frameworkData && (
          <ResearchFrameworkPanel data={frameworkData} compact language={language} />
        )}
        {investmentConclusion && (
          <div className="p-3 bg-secondary/20 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-text">投资动作</span>
              <span className="text-sm font-medium">
                {investmentConclusion.action || investmentConclusion.position || '观察'}
              </span>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {investmentConclusion && (
        <InvestmentConclusionCard data={investmentConclusion} language={language} />
      )}

      {supplyChain && (
        <SupplyChainPanel data={supplyChain} />
      )}

      {valueScenarios && (
        <ValueScenariosCard data={valueScenarios} />
      )}

      {bayesianData && (
        <BayesianScoreTable data={bayesianData} language={language} />
      )}

      {/* 六维评分概览 */}
      {frameworkData && (
        <ResearchFrameworkPanel data={frameworkData} language={language} />
      )}

      {/* 六维详情（展开指标） */}
      {frameworkData && frameworkData.dimensions && frameworkData.dimensions.length > 0 && (
        <DimensionDetailPanel dimensions={frameworkData.dimensions} showIndicators={true} />
      )}
    </div>
  );
};

export default FiveSectionReportView;
