# -*- coding: utf-8 -*-
"""
五段式长线投研报告编排服务

将贝叶斯评分、产业链分析、价值情景整合为五段式报告结构。

P0 阶段：基础闭环
- 六维评分 + 贝叶斯计算
- 产业链分析（规则 + Agent fallback）
- 长期价值情景（规则 + Agent fallback）
- 五段式报告组装
"""

import asyncio
import inspect
import logging
from typing import Dict, Any, Optional, List, cast

from src.scoring import (
    calculate_bayesian,
    aggregate_framework,
    get_default_weights,
)
from src.services.research_scoring_service import ResearchScoringService

logger = logging.getLogger(__name__)


class ResearchIntegrationService:
    """五段式长线投研报告编排服务"""

    def __init__(self):
        self._scoring_service = ResearchScoringService()

    def generate_five_section_report(
        self,
        stock_code: str,
        stock_name: str,
        market: str = "cn",
        raw_data: Optional[Dict[str, Any]] = None,
        report_id: Optional[int] = None,
        enable_agent_analysis: bool = False,
    ) -> Dict[str, Any]:
        """
        生成五段式长线投研报告

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            market: 市场 (cn/hk/us)
            raw_data: 原始数据（技术面/资金面/基本面等）
            report_id: 关联报告ID
            enable_agent_analysis: 是否启用Agent分析（默认False，P1启用）

        Returns:
            五段式报告结构 dict:
            {
                "investment_conclusion": {...},  # ①
                "supply_chain": {...},           # ②
                "value_scenarios": {...},        # ③
                "bayesian_framework": {...},     # ④
                "research_framework": {...},     # ⑤
            }
        """
        raw_data = raw_data or {}

        # Step 1: 六维评分 + 贝叶斯计算
        scoring_result = self._scoring_service.process(
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            raw_data=raw_data,
            report_id=report_id,
        )

        # Step 2: 产业链分析
        supply_chain_data = self._generate_supply_chain(
            stock_code, stock_name, raw_data, enable_agent_analysis
        )

        # Step 3: 长期价值情景
        value_data = self._generate_value_scenarios(
            stock_code, stock_name, raw_data, enable_agent_analysis
        )

        # Step 4: 组装五段式报告
        five_section_report = self._assemble_five_section_report(
            stock_code=stock_code,
            stock_name=stock_name,
            scoring_result=scoring_result,
            supply_chain_data=supply_chain_data,
            value_data=value_data,
            raw_data=raw_data,
        )

        return five_section_report

    def _generate_supply_chain(
        self,
        stock_code: str,
        stock_name: str,
        raw_data: Dict[str, Any],
        enable_agent: bool,
    ) -> Dict[str, Any]:
        """
        生成产业链解读数据

        优先级：
        1. Agent分析结果（如果enable_agent=True）
        2. 规则生成（基于raw_data中的供应链信息）
        3. 默认占位数据
        """
        if enable_agent:
            try:
                agent_coro = self._scoring_service.analyze_supply_chain_agent(
                    stock_code, stock_name, raw_data
                )
                result = (
                    asyncio.run(agent_coro)
                    if inspect.iscoroutine(agent_coro)
                    else agent_coro
                )
                if result.get("success"):
                    return self._transform_supply_chain_from_agent(
                        result.get("analysis", {})
                    )
            except Exception as e:
                logger.warning(f"[ResearchIntegration] Agent supply chain failed: {e}")

        return self._generate_supply_chain_from_rules(stock_code, raw_data)

    def _generate_supply_chain_from_rules(
        self, stock_code: str, raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """基于规则生成产业链数据（无Agent时使用）"""
        stock_name = raw_data.get("stock_name", "公司")
        fundamental_text = raw_data.get("fundamental_analysis", "")
        chain_position = raw_data.get("chain_position", "中游")
        moat_type = raw_data.get("moat_type", "技术")
        moat_strength = raw_data.get("moat_strength", "中等")

        chain_map = [
            {"level": "下游", "companies": ["终端厂商"], "concentration": "分散"},
            {
                "level": "中游",
                "companies": [stock_name],
                "concentration": "集中",
            },
            {"level": "上游", "companies": ["原材料供应商"], "concentration": "中等"},
        ]

        chokepoints = []
        if moat_type == "专利":
            chokepoints.append(
                {
                    "type": "patent",
                    "description": f"{moat_strength}专利壁垒",
                    "confidence": "medium",
                }
            )
        elif moat_type == "技术":
            chokepoints.append(
                {
                    "type": "tech",
                    "description": f"{moat_strength}技术壁垒",
                    "confidence": "medium",
                }
            )

        suppliers = []
        customers = []
        us_china_chain = {
            "role": "待分析",
            "substitution_progress": "待分析",
            "sanction_risk": "待分析",
            "dual_chain_impact": "待分析",
        }
        industry_drivers = []
        company_position = chain_position

        try:
            tushare_data = self._scoring_service.get_supply_chain_from_tushare(
                stock_code
            )
            suppliers = tushare_data.get("suppliers", [])
            customers = tushare_data.get("customers", [])
        except Exception as e:
            logger.warning(f"[ResearchIntegration] Tushare supply chain failed: {e}")

        if fundamental_text and len(fundamental_text) > 100:
            try:
                llm_result = (
                    self._scoring_service.extract_supply_chain_from_annual_report(
                        stock_code, stock_name, fundamental_text
                    )
                )
                if llm_result:
                    if llm_result.get("chain_position"):
                        company_position = llm_result.get("chain_position")
                    if llm_result.get("chokepoint_type"):
                        chokepoints.append(
                            {
                                "type": llm_result.get("chokepoint_type"),
                                "description": llm_result.get("chokepoint_desc", ""),
                                "confidence": "medium",
                            }
                        )
                    if llm_result.get("us_business_ratio"):
                        us_china_chain = {
                            "role": f"美国业务占比{llm_result.get('us_business_ratio')}",
                            "substitution_progress": llm_result.get(
                                "substitution_progress", "待分析"
                            ),
                            "sanction_risk": llm_result.get("sanction_risk", "待观察"),
                            "dual_chain_impact": "待分析",
                        }
                    elif llm_result.get("sanction_risk"):
                        us_china_chain = {
                            "role": "待分析",
                            "substitution_progress": llm_result.get(
                                "substitution_progress", ""
                            ),
                            "sanction_risk": llm_result.get("sanction_risk"),
                            "dual_chain_impact": "待分析",
                        }
                    if llm_result.get("industry_drivers"):
                        industry_drivers = llm_result.get("industry_drivers", [])
            except Exception as e:
                logger.warning(f"[ResearchIntegration] LLM extraction failed: {e}")

        return {
            "chain_map": chain_map,
            "chokepoints": chokepoints,
            "company_position": company_position,
            "upstream": suppliers,
            "downstream": customers,
            "bargaining_power": f"{company_position}议价能力中等",
            "us_china_chain": us_china_chain,
            "industry_drivers": industry_drivers,
        }

    def _transform_supply_chain_from_agent(
        self, agent_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将Agent输出转换为供应链数据结构"""
        chain_position_map = {
            "bottleneck": "瓶颈节点",
            "upstream": "上游",
            "midstream": "中游",
            "downstream": "下游",
            "commodity": "大宗商品",
        }

        chokepoint_type_map = {
            "patent": "专利",
            "capacity": "产能",
            "geo": "地理",
            "tech": "技术",
            "cert": "认证",
            "network": "网络效应",
        }

        chain_position = agent_data.get("chain_position", "中游")
        chain_position_display = chain_position_map.get(chain_position, chain_position)

        chokepoints = []
        cp_type = agent_data.get("chokepoint_type", "none")
        if cp_type and cp_type != "none":
            chokepoints.append(
                {
                    "type": cp_type,
                    "description": agent_data.get("chokepoint_rationale", ""),
                    "confidence": "high",
                }
            )

        us_china_risk_map = {"high": "高", "medium": "中", "low": "低", "none": "无"}

        return {
            "chain_map": [
                {"level": "下游", "companies": ["终端厂商"], "concentration": "分散"},
                {
                    "level": chain_position_display,
                    "companies": [agent_data.get("stock_name", "公司")],
                    "concentration": "集中",
                },
                {
                    "level": "上游",
                    "companies": ["原材料供应商"],
                    "concentration": "中等",
                },
            ],
            "chokepoints": chokepoints,
            "company_position": chain_position_display,
            "upstream": ["原材料供应商"],
            "downstream": ["下游客户"],
            "bargaining_power": agent_data.get("moat_rationale", ""),
            "us_china_chain": {
                "role": "中国链"
                if agent_data.get("us_china_risk") != "none"
                else "双链中立",
                "substitution_progress": "国产替代中"
                if agent_data.get("us_china_risk") == "medium"
                else "已完成",
                "sanction_risk": us_china_risk_map.get(
                    agent_data.get("us_china_risk", "none"), "中"
                ),
                "dual_chain_impact": "中性",
            },
            "industry_drivers": agent_data.get("key_insights", []),
        }

    def _generate_value_scenarios(
        self,
        stock_code: str,
        stock_name: str,
        raw_data: Dict[str, Any],
        enable_agent: bool,
    ) -> Dict[str, Any]:
        """
        生成长期价值情景数据

        优先级：
        1. Agent分析结果（如果enable_agent=True）
        2. 规则生成（基于raw_data中的估值信息）
        3. 默认占位数据
        """
        if enable_agent:
            try:
                agent_coro = self._scoring_service.analyze_value_agent(
                    stock_code, stock_name, raw_data
                )
                result = (
                    asyncio.run(agent_coro)
                    if inspect.iscoroutine(agent_coro)
                    else agent_coro
                )
                if result.get("success"):
                    return self._transform_value_from_agent(result.get("analysis", {}))
            except Exception as e:
                logger.warning(
                    f"[ResearchIntegration] Agent value analysis failed: {e}"
                )

        return self._generate_value_from_rules(raw_data)

    def _generate_value_from_rules(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """基于规则生成价值情景数据"""
        pe_percentile = raw_data.get("pe_percentile", 50)
        current_price = raw_data.get("current_price", 100)

        if pe_percentile < 30:
            valuation_label = "低估"
            scenario_adjust = 1.3
        elif pe_percentile > 70:
            valuation_label = "高估"
            scenario_adjust = 0.7
        else:
            valuation_label = "中性"
            scenario_adjust = 1.0

        base_value = current_price * scenario_adjust

        return {
            "industry_space": f"产业空间：{valuation_label}，受益于产业升级",
            "competitive_evolution": "竞争格局：头部集中，强者恒强",
            "scenarios": [
                {
                    "type": "optimistic",
                    "probability": 0.25,
                    "value_anchor": round(base_value * 1.5, 2),
                    "description": "乐观情景：市场份额提升，盈利能力显著改善",
                },
                {
                    "type": "neutral",
                    "probability": 0.50,
                    "value_anchor": round(base_value, 2),
                    "description": "中性情景：稳定增长，维持现状",
                },
                {
                    "type": "pessimistic",
                    "probability": 0.25,
                    "value_anchor": round(base_value * 0.7, 2),
                    "description": "悲观情景：竞争加剧，盈利能力下降",
                },
            ],
            "horizons": {
                "horizon_1y": f"¥{round(base_value * 1.1, 2):.2f}",
                "horizon_3y": f"¥{round(base_value * 1.3, 2):.2f}",
                "horizon_5y": f"¥{round(base_value * 1.6, 2):.2f}",
            },
            "catalysts": ["产业政策利好", "新产能投放", "市场份额提升"],
            "risks": ["竞争加剧", "原材料价格上涨", "需求不及预期"],
        }

    def _transform_value_from_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """将Agent输出转换为价值情景数据结构"""
        value_horizons = agent_data.get("value_horizons", {})
        scenarios_data = agent_data.get("scenarios", {})

        scenarios = []
        for scenario_key, scenario_type in [
            ("bull_case", "optimistic"),
            ("base_case", "neutral"),
            ("bear_case", "pessimistic"),
        ]:
            scenario_info = scenarios_data.get(scenario_key, {})
            if scenario_info:
                scenarios.append(
                    {
                        "type": scenario_type,
                        "probability": scenario_info.get("probability", 0.33),
                        "value_anchor": scenario_info.get("value_anchor"),
                        "description": scenario_info.get("key_assumptions", []),
                    }
                )

        return {
            "industry_space": f"产业空间：受益于行业增长",
            "competitive_evolution": "竞争格局：头部集中趋势",
            "scenarios": scenarios
            if scenarios
            else self._generate_value_from_rules({}).get("scenarios", []),
            "horizons": value_horizons,
            "catalysts": agent_data.get("catalysts", []),
            "risks": agent_data.get("risks", []),
        }

    def _assemble_five_section_report(
        self,
        stock_code: str,
        stock_name: str,
        scoring_result: Dict[str, Any],
        supply_chain_data: Dict[str, Any],
        value_data: Dict[str, Any],
        raw_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        组装五段式报告

        五段结构：
        ① 投资结论 - investment_conclusion
        ② 产业链解读 - supply_chain
        ③ 长期价值与情景 - value_scenarios
        ④ 贝叶斯评分表 - bayesian_framework
        ⑤ 六维评分详情 - research_framework
        """
        framework = scoring_result.get("framework_score", {})
        bayesian = scoring_result.get("bayesian_result", {})

        dimension_total = framework.get("dimension_total", 50)
        prior_p = bayesian.get("prior_p", 0.5)
        market_implied_p = bayesian.get("market_implied_p", 0.5)
        edge = bayesian.get("edge", 0)
        posterior_p = bayesian.get("posterior_p", 0.5)
        position_suggestion = bayesian.get("position_suggestion", "观察")

        horizons = value_data.get("horizons", {})

        # ① 投资结论
        investment_conclusion = {
            "prior_p": prior_p,
            "market_implied_p": market_implied_p,
            "edge": edge,
            "posterior_p": posterior_p,
            "position": position_suggestion,
            "action": self._map_action_from_edge(edge),
            "chain_position_summary": supply_chain_data.get("company_position"),
            "value_range_1y": horizons.get("horizon_1y"),
            "value_range_3y": horizons.get("horizon_3y"),
            "value_range_5y": horizons.get("horizon_5y"),
            "rationale": supply_chain_data.get("bargaining_power")
            or value_data.get("industry_space"),
        }

        # ② 产业链解读（已在_generate_supply_chain生成）
        supply_chain = {
            "chain_map": supply_chain_data.get("chain_map", []),
            "chokepoints": supply_chain_data.get("chokepoints", []),
            "company_position": supply_chain_data.get("company_position", ""),
            "upstream": supply_chain_data.get("upstream", []),
            "downstream": supply_chain_data.get("downstream", []),
            "bargaining_power": supply_chain_data.get("bargaining_power"),
            "us_china_chain": supply_chain_data.get("us_china_chain"),
            "industry_drivers": supply_chain_data.get("industry_drivers", []),
        }

        # ③ 长期价值与情景
        value_scenarios = {
            "industry_space": value_data.get("industry_space"),
            "competitive_evolution": value_data.get("competitive_evolution"),
            "scenarios": value_data.get("scenarios", []),
            "horizons": value_data.get("horizons"),
            "catalysts": value_data.get("catalysts", []),
            "risks": value_data.get("risks", []),
        }

        # ④ 贝叶斯评分表
        bayesian_framework = {
            "prior_p": prior_p,
            "market_implied_p": market_implied_p,
            "edge": edge,
            "posterior_p": posterior_p,
            "position_suggestion": position_suggestion,
            "confidence": self._map_confidence(edge),
            "stop_conditions": bayesian.get("stop_conditions"),
        }

        # ⑤ 六维评分
        research_framework = {
            "dimension_total": dimension_total,
            "dimensions": framework.get("dimensions", []),
            "scoring_version": framework.get("version", "v1"),
        }

        return {
            "investment_conclusion": investment_conclusion,
            "supply_chain": supply_chain,
            "value_scenarios": value_scenarios,
            "bayesian_framework": bayesian_framework,
            "research_framework": research_framework,
        }

    def _map_action_from_edge(self, edge: float) -> str:
        """根据Edge映射投资动作"""
        if edge > 0.3:
            return "建仓"
        elif edge > 0.15:
            return "加仓"
        elif edge > 0:
            return "持有"
        elif edge > -0.15:
            return "观察"
        else:
            return "减仓"

    def _map_confidence(self, edge: float) -> str:
        """根据Edge映射置信度"""
        if abs(edge) > 0.3:
            return "高"
        elif abs(edge) > 0.15:
            return "中"
        else:
            return "低"
