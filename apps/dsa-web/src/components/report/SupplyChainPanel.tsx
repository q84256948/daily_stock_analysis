import React from 'react';
import { Card } from '../common';

interface SupplyChainPanelProps {
  data?: {
    companyPosition?: string;
    upstreamSuppliers?: string[];
    downstreamCustomers?: string[];
    chokepoints?: Array<{
      type: string;
      description: string;
      confidence?: 'high' | 'medium' | 'low';
    }>;
    usChinaChain?: {
      role?: string;
      substitutionProgress?: string;
      sanctionRisk?: string;
      dualChainImpact?: string;
    };
    industryDrivers?: string[];
    chainMap?: Array<{
      level: string;
      companies?: string[];
      concentration?: string;
    }>;
  };
}

const getConfidenceColor = (confidence?: string): string => {
  switch (confidence) {
    case 'high':
      return 'var(--home-price-up)';
    case 'medium':
      return 'var(--home-accent)';
    case 'low':
      return 'var(--home-price-down)';
    default:
      return 'var(--text-muted)';
  }
};

const getChokepointIcon = (type: string): string => {
  switch (type.toLowerCase()) {
    case 'patent':
      return '🔐';
    case 'capacity':
      return '🏭';
    case 'tech':
      return '⚙️';
    case 'geo':
      return '🌍';
    case 'cert':
      return '📋';
    default:
      return '⚡';
  }
};

export const SupplyChainPanel: React.FC<SupplyChainPanelProps> = ({ data }) => {
  if (!data) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center text-muted-text text-sm py-4">
          暂无产业链数据
        </div>
      </Card>
    );
  }

  const {
    companyPosition,
    upstreamSuppliers = [],
    downstreamCustomers = [],
    chokepoints = [],
    usChinaChain,
    industryDrivers = [],
    chainMap = [],
  } = data;

  return (
    <div className="space-y-4">
      {/* ② 产业链解读 */}
      <Card variant="bordered" padding="md">
        <h3 className="text-base font-semibold mb-3 text-foreground">② 产业链解读</h3>

        {/* 供应链地图 */}
        {chainMap.length > 0 && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">供应链地图</div>
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              {chainMap.map((node, idx) => (
                <React.Fragment key={idx}>
                  <div className="flex-shrink-0 text-center px-3 py-2 bg-secondary/30 rounded-lg min-w-[80px]">
                    <div className="text-xs text-muted-text">{node.level}</div>
                    {node.companies && node.companies.length > 0 && (
                      <div className="text-xs mt-1 truncate max-w-[100px]">
                        {node.companies[0]}
                      </div>
                    )}
                  </div>
                  {idx < chainMap.length - 1 && (
                    <span className="text-muted-text flex-shrink-0">→</span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {/* 公司定位 */}
        {companyPosition && (
          <div className="mb-4 p-3 bg-primary/10 rounded-lg">
            <div className="text-xs text-muted-text mb-1">公司定位</div>
            <div className="text-sm">{companyPosition}</div>
          </div>
        )}

        {/* 上下游关系 */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="p-2 bg-secondary/20 rounded">
            <div className="text-xs text-muted-text mb-1">上游供应商</div>
            {upstreamSuppliers.length > 0 ? (
              <div className="text-sm space-y-1">
                {upstreamSuppliers.slice(0, 3).map((s, idx) => (
                  <div key={idx} className="truncate">{s}</div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-text">暂无数据</div>
            )}
          </div>
          <div className="p-2 bg-secondary/20 rounded">
            <div className="text-xs text-muted-text mb-1">下游客户</div>
            {downstreamCustomers.length > 0 ? (
              <div className="text-sm space-y-1">
                {downstreamCustomers.slice(0, 3).map((c, idx) => (
                  <div key={idx} className="truncate">{c}</div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-text">暂无数据</div>
            )}
          </div>
        </div>

        {/* 瓶颈点 */}
        {chokepoints.length > 0 && (
          <div className="mb-4">
            <div className="text-xs text-muted-text mb-2">瓶颈点分析</div>
            <div className="grid grid-cols-1 gap-2">
              {chokepoints.map((cp, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 p-2 bg-secondary/20 rounded"
                >
                  <span className="text-lg">{getChokepointIcon(cp.type)}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium capitalize">{cp.type}</span>
                      {cp.confidence && (
                        <span
                          className="text-xs px-1 rounded"
                          style={{ backgroundColor: `${getConfidenceColor(cp.confidence)}20`, color: getConfidenceColor(cp.confidence) }}
                        >
                          {cp.confidence === 'high' ? '高可信' : cp.confidence === 'medium' ? '中可信' : '低可信'}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-text mt-1">{cp.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 中美双链 */}
        {usChinaChain && (
          <div className="mb-4 p-3 bg-secondary/20 rounded-lg">
            <div className="text-xs text-muted-text mb-2">中美双链位置</div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-muted-text">角色：</span>
                <span className="font-medium">{usChinaChain.role || '-'}</span>
              </div>
              <div>
                <span className="text-muted-text">制裁风险：</span>
                <span className="font-medium">{usChinaChain.sanctionRisk || '-'}</span>
              </div>
              <div>
                <span className="text-muted-text">国产替代：</span>
                <span className="font-medium">{usChinaChain.substitutionProgress || '-'}</span>
              </div>
              <div>
                <span className="text-muted-text">双链影响：</span>
                <span className="font-medium">{usChinaChain.dualChainImpact || '-'}</span>
              </div>
            </div>
          </div>
        )}

        {/* 产业驱动 */}
        {industryDrivers.length > 0 && (
          <div>
            <div className="text-xs text-muted-text mb-2">产业驱动根因</div>
            <div className="flex flex-wrap gap-2">
              {industryDrivers.map((driver, idx) => (
                <span key={idx} className="px-2 py-1 bg-primary/10 rounded text-xs">
                  {driver}
                </span>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default SupplyChainPanel;
