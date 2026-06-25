# -*- coding: utf-8 -*-
"""
P3 Validation Tests for SupplyChainAgent and ValueAgent.

Validates the P3 components:
1. SupplyChainAgent
2. ValueAgent
3. Value scenario prompts
4. Agent integration in ResearchScoringService
5. Frontend AgentAnalysisPanel
"""

import json
import sys
import os

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)


class TestRunner:
    """P3 validation test runner"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def check(self, name: str, condition: bool, message: str = ""):
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}")
            return True
        else:
            self.failed += 1
            error_msg = f"  [FAIL] {name}"
            if message:
                error_msg += f" - {message}"
            self.errors.append(error_msg)
            print(error_msg)
            return False

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"P3 Validation Results: {self.passed}/{total} passed")
        if self.errors:
            print("\nFailures:")
            for e in self.errors:
                print(e)
        print(f"{'=' * 60}")
        return self.failed == 0


def test_value_prompts(runner: TestRunner):
    """Test value scenario prompts"""
    print("\n[Test 1] Value Scenario Prompts")

    try:
        from src.agents.prompts.value_prompts import (
            build_value_scenario_prompt,
            VALUE_SCENARIO_ANALYSIS_PROMPT,
            VALUE_SUMMARY_PROMPT,
        )

        runner.check(
            "VALUE_SCENARIO_ANALYSIS_PROMPT exists",
            isinstance(VALUE_SCENARIO_ANALYSIS_PROMPT, str)
            and len(VALUE_SCENARIO_ANALYSIS_PROMPT) > 0,
        )

        runner.check(
            "VALUE_SUMMARY_PROMPT exists",
            isinstance(VALUE_SUMMARY_PROMPT, str) and len(VALUE_SUMMARY_PROMPT) > 0,
        )

        prompt = build_value_scenario_prompt(
            stock_code="600519",
            stock_name="贵州茅台",
            industry="白酒",
            pe=35.0,
            pb=12.0,
            roe=30.0,
            revenue_growth=15.0,
            current_price=1850.0,
        )

        runner.check(
            "build_value_scenario_prompt returns string",
            isinstance(prompt, str),
        )

        runner.check(
            "build_value_scenario_prompt includes stock code",
            "600519" in prompt,
        )

        runner.check(
            "build_value_scenario_prompt includes PE",
            "35.0" in prompt or "35" in prompt,
        )

        runner.check(
            "build_value_scenario_prompt includes value horizons",
            "value_horizons" in prompt.lower(),
        )

        runner.check(
            "build_value_scenario_prompt includes scenarios",
            "scenarios" in prompt.lower() or "scenario" in prompt.lower(),
        )

    except Exception as e:
        runner.check(f"Value prompts test: {e}", False, str(e))


def test_supply_chain_agent(runner: TestRunner):
    """Test SupplyChainAgent class"""
    print("\n[Test 2] SupplyChainAgent")

    try:
        from src.agent.agents.supply_chain_agent import SupplyChainAgent

        runner.check(
            "SupplyChainAgent class exists",
            SupplyChainAgent is not None,
        )

        runner.check(
            "SupplyChainAgent has agent_name",
            hasattr(SupplyChainAgent, "agent_name")
            and SupplyChainAgent.agent_name == "supply_chain",
        )

        runner.check(
            "SupplyChainAgent has max_steps",
            hasattr(SupplyChainAgent, "max_steps"),
        )

        runner.check(
            "SupplyChainAgent has tool_names",
            hasattr(SupplyChainAgent, "tool_names"),
        )

        runner.check(
            "SupplyChainAgent has system_prompt method",
            hasattr(SupplyChainAgent, "system_prompt"),
        )

        runner.check(
            "SupplyChainAgent has build_user_message method",
            hasattr(SupplyChainAgent, "build_user_message"),
        )

        runner.check(
            "SupplyChainAgent has post_process method",
            hasattr(SupplyChainAgent, "post_process"),
        )

        runner.check(
            "SupplyChainAgent.tool_names includes required tools",
            "get_stock_info" in SupplyChainAgent.tool_names,
        )

    except ImportError as e:
        runner.check(f"SupplyChainAgent import: {e}", False, str(e))
    except Exception as e:
        runner.check(f"SupplyChainAgent test: {e}", False, str(e))


def test_value_agent(runner: TestRunner):
    """Test ValueAgent class"""
    print("\n[Test 3] ValueAgent")

    try:
        from src.agent.agents.value_agent import ValueAgent

        runner.check(
            "ValueAgent class exists",
            ValueAgent is not None,
        )

        runner.check(
            "ValueAgent has agent_name",
            hasattr(ValueAgent, "agent_name") and ValueAgent.agent_name == "value",
        )

        runner.check(
            "ValueAgent has max_steps",
            hasattr(ValueAgent, "max_steps"),
        )

        runner.check(
            "ValueAgent has tool_names",
            hasattr(ValueAgent, "tool_names"),
        )

        runner.check(
            "ValueAgent has system_prompt method",
            hasattr(ValueAgent, "system_prompt"),
        )

        runner.check(
            "ValueAgent has build_user_message method",
            hasattr(ValueAgent, "build_user_message"),
        )

        runner.check(
            "ValueAgent has post_process method",
            hasattr(ValueAgent, "post_process"),
        )

        runner.check(
            "ValueAgent.tool_names includes required tools",
            "get_stock_info" in ValueAgent.tool_names,
        )

    except ImportError as e:
        runner.check(f"ValueAgent import: {e}", False, str(e))
    except Exception as e:
        runner.check(f"ValueAgent test: {e}", False, str(e))


def test_agent_registration(runner: TestRunner):
    """Test agents are properly registered"""
    print("\n[Test 4] Agent Registration")

    try:
        from src.agent.agents import SupplyChainAgent, ValueAgent

        runner.check(
            "SupplyChainAgent can be imported from agents",
            SupplyChainAgent is not None,
        )

        runner.check(
            "ValueAgent can be imported from agents",
            ValueAgent is not None,
        )

    except ImportError as e:
        runner.check(f"Agent registration: {e}", False, str(e))


def test_service_integration(runner: TestRunner):
    """Test ResearchScoringService integration"""
    print("\n[Test 5] Service Integration")

    try:
        from src.services.research_scoring_service import ResearchScoringService

        runner.check(
            "ResearchScoringService exists",
            ResearchScoringService is not None,
        )

        service = ResearchScoringService()

        runner.check(
            "ResearchScoringService has _init_agents method",
            hasattr(service, "_init_agents"),
        )

        runner.check(
            "ResearchScoringService has analyze_supply_chain_agent method",
            hasattr(service, "analyze_supply_chain_agent"),
        )

        runner.check(
            "ResearchScoringService has analyze_value_agent method",
            hasattr(service, "analyze_value_agent"),
        )

        runner.check(
            "ResearchScoringService has enrich_with_agent_analysis method",
            hasattr(service, "enrich_with_agent_analysis"),
        )

        runner.check(
            "ResearchScoringService has get_agent_tools_available method",
            hasattr(service, "get_agent_tools_available"),
        )

        runner.check(
            "get_agent_tools_available returns dict",
            isinstance(service.get_agent_tools_available(), dict),
        )

    except ImportError as e:
        runner.check(f"Service integration: {e}", False, str(e))
    except Exception as e:
        runner.check(f"Service integration test: {e}", False, str(e))


def test_frontend_component(runner: TestRunner):
    """Test frontend AgentAnalysisPanel component"""
    print("\n[Test 6] Frontend AgentAnalysisPanel")

    frontend_path = os.path.join(
        project_root,
        "apps",
        "dsa-web",
        "src",
        "components",
        "report",
        "AgentAnalysisPanel.tsx",
    )

    runner.check(
        "AgentAnalysisPanel.tsx exists",
        os.path.exists(frontend_path),
    )

    if os.path.exists(frontend_path):
        with open(frontend_path, "r") as f:
            content = f.read()

        runner.check(
            "AgentAnalysisPanel has SupplyChainAnalysis interface",
            "SupplyChainAnalysis" in content,
        )

        runner.check(
            "AgentAnalysisPanel has ValueAnalysis interface",
            "ValueAnalysis" in content,
        )

        runner.check(
            "AgentAnalysisPanel has value scenarios",
            "scenarios" in content.lower(),
        )

        runner.check(
            "AgentAnalysisPanel has bull/base/bear case rendering",
            "bull_case" in content
            and "base_case" in content
            and "bear_case" in content,
        )

        runner.check(
            "AgentAnalysisPanel has value horizons",
            "value_horizons" in content.lower(),
        )

        runner.check(
            "AgentAnalysisPanel exports component",
            "export const AgentAnalysisPanel" in content or "export default" in content,
        )


def test_e2e_scenario(runner: TestRunner):
    """End-to-end scenario test"""
    print("\n[Test 7] End-to-End Scenario")

    try:
        from src.agents.prompts.value_prompts import build_value_scenario_prompt
        from src.agent.agents import SupplyChainAgent, ValueAgent

        prompt = build_value_scenario_prompt(
            stock_code="600176",
            stock_name="中国巨石",
            industry="玻纤",
            pe=12.0,
            pb=2.5,
            roe=18.0,
            revenue_growth=20.0,
            current_price=15.5,
        )

        runner.check(
            "E2E: Value prompt generated",
            isinstance(prompt, str) and len(prompt) > 100,
        )

        runner.check(
            "E2E: SupplyChainAgent class available",
            SupplyChainAgent is not None,
        )

        runner.check(
            "E2E: ValueAgent class available",
            ValueAgent is not None,
        )

        runner.check(
            "E2E: Agent name correct",
            SupplyChainAgent.agent_name == "supply_chain"
            and ValueAgent.agent_name == "value",
        )

    except Exception as e:
        runner.check(f"E2E scenario: {e}", False, str(e))


def main():
    """Run all P3 validation tests"""
    print("=" * 60)
    print("P3 Validation: SupplyChainAgent & ValueAgent")
    print("=" * 60)

    runner = TestRunner()

    test_value_prompts(runner)
    test_supply_chain_agent(runner)
    test_value_agent(runner)
    test_agent_registration(runner)
    test_service_integration(runner)
    test_frontend_component(runner)
    test_e2e_scenario(runner)

    success = runner.summary()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
