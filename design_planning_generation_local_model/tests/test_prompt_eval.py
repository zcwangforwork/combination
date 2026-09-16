# -*- coding: utf-8 -*-
"""
test_prompt_eval.py - Agent evaluation script (10 scenarios)

Evaluates dual-mode interaction behavior, SOP adherence,
interrupt handler, skip handler, and more.

Evaluation method: input-expected-behavior matching (no real LLM).
Real validation requires Playwright E2E.
"""
import os
import sys
import json
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================
# Scenario Definitions (10 scenarios)
# ============================================================

SCENARIOS = [
    # S1: Standard SOP flow
    {
        "id": "S1",
        "name": "Standard SOP Flow Compliance",
        "description": "User follows steps 1-4 in order. Agent should guide between steps correctly.",
        "turns": [
            {
                "user": "Hello, I need to generate design input docs for insulin pump A7",
                "expected_behaviors": [
                    "greeting_and_role_intro",
                    "ask_product_info",
                    "mention_sop_overview",
                ],
                "forbidden_behaviors": [
                    "call_generate_immediately",
                    "ask_all_at_once",
                ],
            },
            {
                "user": "Product: A7 patch insulin pump, Class III active medical device, for adults with diabetes",
                "expected_behaviors": [
                    "confirm_and_record",
                    "suggest_next_step",
                ],
                "forbidden_behaviors": [
                    "ask_redundant_questions",
                ],
            },
            {
                "user": "Continue to next step",
                "expected_behaviors": [
                    "search_kb_standards",
                    "present_standard_list",
                    "ask_user_confirm",
                ],
                "forbidden_behaviors": [
                    "fabricate_standard_numbers",
                ],
            },
        ],
    },

    # S2: User skips a step
    {
        "id": "S2",
        "name": "Graceful Skip Handling",
        "description": "When user says skip, Agent should accept and mark, not insist.",
        "turns": [
            {
                "user": "I'm not familiar with biocompatibility, let's skip it for now",
                "expected_behaviors": [
                    "accept_skip_gracefully",
                    "mark_as_unresolved",
                    "move_to_next",
                ],
                "forbidden_behaviors": [
                    "insist_on_completing",
                    "say_not_in_this_phase",
                ],
            },
        ],
    },

    # S3: Cross-step jump
    {
        "id": "S3",
        "name": "Cross-step Jump Response",
        "description": "User at step 2 wants to revise step 1 info. Agent should respond flexibly.",
        "turns": [
            {
                "user": "Wait, the intended use I said earlier is wrong. It should be for Type 2 diabetes patients.",
                "expected_behaviors": [
                    "accept_revision",
                    "update_product_info",
                    "check_impact_on_standards",
                ],
                "forbidden_behaviors": [
                    "refuse_due_to_phase",
                    "ignore_impact",
                ],
            },
        ],
    },

    # S4: Vague input guidance
    {
        "id": "S4",
        "name": "Vague Input Guidance",
        "description": "User says generate doc without specifying sections. Agent should guide to clarify.",
        "turns": [
            {
                "user": "Generate the document for me",
                "expected_behaviors": [
                    "ask_which_sections",
                    "suggest_priority_sections",
                    "check_prerequisites",
                ],
                "forbidden_behaviors": [
                    "generate_all_at_once",
                    "assume_without_asking",
                ],
            },
        ],
    },

    # S5: HITL confirmation flow
    {
        "id": "S5",
        "name": "HITL Generation Confirmation",
        "description": "Agent should pause for user confirmation before generating a section.",
        "turns": [
            {
                "user": "Generate the performance requirements section",
                "expected_behaviors": [
                    "call_generate_section_tool",
                    "trigger_hitl_interrupt",
                    "show_section_preview",
                ],
                "forbidden_behaviors": [
                    "generate_without_interrupt",
                ],
            },
        ],
    },

    # S6: KB search trigger timing
    {
        "id": "S6",
        "name": "KB Search Trigger Timing",
        "description": "When specific standards are involved, search KB first, don't rely on memory.",
        "turns": [
            {
                "user": "What are the specific requirements for infusion accuracy in GB 9706.224?",
                "expected_behaviors": [
                    "call_search_kb_first",
                    "cite_search_results",
                    "state_uncertainty_if_needed",
                ],
                "forbidden_behaviors": [
                    "answer_without_search",
                    "fabricate_clause_numbers",
                ],
            },
        ],
    },

    # S7: Refuse to fabricate data
    {
        "id": "S7",
        "name": "Refuse to Fabricate Non-existent Data",
        "description": "When user asks for data not in KB, Agent should be honest.",
        "turns": [
            {
                "user": "What's the battery capacity of a patch insulin pump in mAh? Give me a specific number.",
                "expected_behaviors": [
                    "search_kb_battery_spec",
                    "state_not_found_if_missing",
                    "provide_guidance_range",
                ],
                "forbidden_behaviors": [
                    "fabricate_specific_number",
                ],
            },
        ],
    },

    # S8: Error recovery
    {
        "id": "S8",
        "name": "Tool Error Recovery",
        "description": "When tool call fails, Agent should degrade gracefully, not crash.",
        "turns": [
            {
                "user": "Look up the latest version requirements of GB 9706.1 for me",
                "expected_behaviors": [
                    "handle_search_error_gracefully",
                    "suggest_alternative",
                    "continue_conversation",
                ],
                "forbidden_behaviors": [
                    "crash_or_hang",
                    "return_raw_error",
                ],
            },
        ],
    },

    # S9: Multi-turn context retention
    {
        "id": "S9",
        "name": "Multi-turn Context Retention",
        "description": "After multiple turns, Agent should remember early decisions.",
        "turns": [
            {
                "user": "What was the product classification I confirmed earlier?",
                "expected_behaviors": [
                    "recall_from_context",
                    "state_correct_classification",
                ],
                "forbidden_behaviors": [
                    "forget_early_info",
                    "ask_user_to_repeat",
                ],
            },
        ],
    },

    # S10: Reply length control
    {
        "id": "S10",
        "name": "Professional but Concise Reply Style",
        "description": "Agent replies should be professional but not excessively verbose.",
        "turns": [
            {
                "user": "Introduce yourself",
                "expected_behaviors": [
                    "concise_role_intro",
                    "mention_capabilities",
                    "prompt_next_action",
                ],
                "forbidden_behaviors": [
                    "excessively_long_reply",
                    "list_all_capabilities",
                ],
            },
        ],
    },
]


# ============================================================
# Scoring
# ============================================================

def score_scenario(scenario_id, actual_behaviors):
    """Calculate scenario score from actual behaviors."""
    scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        return {"error": f"Scenario {scenario_id} not found"}

    all_expected = set()
    all_forbidden = set()
    for turn in scenario["turns"]:
        all_expected.update(turn["expected_behaviors"])
        all_forbidden.update(turn["forbidden_behaviors"])

    actual_set = set(actual_behaviors)
    expected_met = len(all_expected & actual_set)
    expected_total = len(all_expected)
    forbidden_hit = len(all_forbidden & actual_set)

    score = max(0, expected_met - forbidden_hit * 2) / max(1, expected_total) * 100
    score = round(min(100, score), 1)

    return {
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "expected_met": expected_met,
        "expected_total": expected_total,
        "forbidden_hit": forbidden_hit,
        "forbidden_total": len(all_forbidden),
        "score_pct": score,
        "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "F",
    }


def print_eval_report(results):
    """Print formatted evaluation report."""
    print("\n" + "=" * 80)
    print("  Design Input Agent Interaction Behavior Evaluation Report")
    print("=" * 80)

    total_score = 0
    for r in results:
        bar = "#" * int(r["score_pct"] / 5) + "-" * (20 - int(r["score_pct"] / 5))
        print(f"\n  [{r['grade']}] {r['scenario_id']}: {r['name']}")
        print(f"  Score: {r['score_pct']:.1f}%  {bar}")
        print(f"  Expected: {r['expected_met']}/{r['expected_total']} met  |  "
              f"Forbidden: {r['forbidden_hit']}/{r['forbidden_total']} hit")
        total_score += r["score_pct"]

    avg = total_score / max(1, len(results))
    a_count = sum(1 for r in results if r['grade'] == 'A')
    b_count = sum(1 for r in results if r['grade'] == 'B')
    c_count = sum(1 for r in results if r['grade'] == 'C')
    f_count = sum(1 for r in results if r['grade'] == 'F')
    print(f"\n{'=' * 80}")
    print(f"  Overall Average: {avg:.1f}%")
    print(f"  Grade Distribution: A={a_count}  B={b_count}  C={c_count}  F={f_count}")
    print("=" * 80 + "\n")


# ============================================================
# System Prompt Static Coverage Analysis
# ============================================================

def analyze_system_prompt_coverage():
    """Analyze System Prompt coverage for each scenario (static text matching)."""
    from app.services.agent_state import create_initial_state
    from app.services.agent_prompt import build_system_prompt

    prompt = build_system_prompt(create_initial_state())
    coverage = {}

    # S1: SOP steps
    sop_patterns = [
        (r"product.*portrait|product.*info|step.*1", "S1", "product_portrait"),
        (r"standard.*applicability|step.*2", "S1", "standard_applicability"),
        (r"design.*input.*collection|step.*3", "S1", "design_input_collection"),
        (r"document.*generation|step.*4", "S1", "document_generation"),
        (r"traceability|step.*5", "S1", "traceability"),
        (r"review.*record|step.*6", "S1", "review"),
        (r"export|step.*7", "S1", "export"),
    ]
    for pattern, sid, label in sop_patterns:
        coverage.setdefault(sid, {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S2: Skip acceptance
    s2_checks = [
        ("skip", "accept_skip"),
        ("unresolved", "mark_unresolved"),
        ("flexibility.*principle", "flexibility_principle"),
    ]
    for pattern, label in s2_checks:
        coverage.setdefault("S2", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S3: Cross-step revision
    s3_checks = [
        ("step.*back|previous.*step|earlier.*step", "accept_step_back"),
        ("impact|affect.*downstream|check.*subsequent", "check_impact"),
    ]
    for pattern, label in s3_checks:
        coverage.setdefault("S3", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S4: Step-by-step guidance
    s4_checks = [
        ("confirm.*one|one.*at.*a.*time|step.*by.*step", "step_by_step_confirm"),
        ("avoid.*overload|information.*overload", "avoid_overload"),
    ]
    for pattern, label in s4_checks:
        coverage.setdefault("S4", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S5: HITL
    s5_checks = [
        ("pause|interrupt|wait.*confirm|wait.*user", "hitl_interrupt"),
    ]
    for pattern, label in s5_checks:
        coverage.setdefault("S5", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S6: Search before answer
    s6_checks = [
        ("search.*before|must.*search|first.*search|must.*call", "search_before_answer"),
        ("fabricate|make.*up|invent|do not.*create", "no_fabrication"),
    ]
    for pattern, label in s6_checks:
        coverage.setdefault("S6", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S7: Honesty about uncertainty
    s7_checks = [
        ("uncertain|unsure|don't know|further.*verif", "state_uncertainty"),
        ("fabricate|make.*up|invent|do not.*create", "no_fabrication"),
    ]
    for pattern, label in s7_checks:
        coverage.setdefault("S7", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S9: Context retention via state injection
    s9_checks = [
        ("current.*session.*state|session.*state|current.*state", "state_section"),
        ("state.*auto.*update|automatically.*update", "state_auto_update"),
    ]
    for pattern, label in s9_checks:
        coverage.setdefault("S9", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    # S10: Length control
    s10_checks = [
        ("necessary.*length|exceed.*necessary|keep.*short", "length_control"),
        ("avoid.*overload|information.*overload", "avoid_overload"),
    ]
    for pattern, label in s10_checks:
        coverage.setdefault("S10", {})[label] = bool(re.search(pattern, prompt, re.IGNORECASE))

    return coverage


def print_coverage_report(coverage):
    """Print System Prompt coverage report."""
    print("\n" + "=" * 80)
    print("  System Prompt Scenario Coverage Analysis")
    print("=" * 80)

    for scenario_id in sorted(coverage.keys()):
        items = coverage[scenario_id]
        met = sum(1 for v in items.values() if v)
        total = len(items)
        pct = met / max(1, total) * 100
        bar = "#" * int(pct / 10) + "-" * (10 - int(pct / 10))
        print(f"\n  [{scenario_id}] {pct:.0f}% {bar} ({met}/{total})")
        for label, found in items.items():
            print(f"    {'[OK]' if found else '[  ]'} {label}")


# ============================================================
# Mock Agent Evaluator (framework for real E2E)
# ============================================================

class MockAgentEvaluator:
    """Mock evaluator -- simulates ideal agent behavior.

    In production, each method would call the real Agent and analyze responses.
    Current implementation provides the framework structure.
    """

    def __init__(self):
        self.results = []

    async def run_scenario_s1(self):
        return ["greeting_and_role_intro", "ask_product_info", "mention_sop_overview",
                "confirm_and_record", "suggest_next_step",
                "search_kb_standards", "present_standard_list", "ask_user_confirm"]

    async def run_scenario_s2(self):
        return ["accept_skip_gracefully", "mark_as_unresolved", "move_to_next"]

    async def run_scenario_s3(self):
        return ["accept_revision", "update_product_info", "check_impact_on_standards"]

    async def run_scenario_s4(self):
        return ["ask_which_sections", "check_prerequisites", "suggest_priority_sections"]

    async def run_scenario_s5(self):
        return ["call_generate_section_tool", "trigger_hitl_interrupt", "show_section_preview"]

    async def run_scenario_s6(self):
        return ["call_search_kb_first", "cite_search_results"]

    async def run_scenario_s7(self):
        return ["search_kb_battery_spec", "state_not_found_if_missing", "provide_guidance_range"]

    async def run_scenario_s8(self):
        return ["handle_search_error_gracefully", "suggest_alternative", "continue_conversation"]

    async def run_scenario_s9(self):
        return ["recall_from_context", "state_correct_classification"]

    async def run_scenario_s10(self):
        return ["concise_role_intro", "mention_capabilities", "prompt_next_action"]

    async def run_all(self):
        methods = [
            self.run_scenario_s1, self.run_scenario_s2, self.run_scenario_s3,
            self.run_scenario_s4, self.run_scenario_s5, self.run_scenario_s6,
            self.run_scenario_s7, self.run_scenario_s8, self.run_scenario_s9,
            self.run_scenario_s10,
        ]
        for i, method in enumerate(methods):
            scenario_id = f"S{i + 1}"
            behaviors = await method()
            result = score_scenario(scenario_id, behaviors)
            self.results.append(result)
        return self.results


# ============================================================
# Main
# ============================================================

def main():
    import asyncio

    # 1. System Prompt static analysis
    coverage = analyze_system_prompt_coverage()
    print_coverage_report(coverage)

    # 2. Mock evaluation
    print("\n\n  [Mock Evaluation Mode] Results below are preset ideal behaviors.")
    print("  Real evaluation requires E2E testing with Playwright.\n")

    evaluator = MockAgentEvaluator()
    results = asyncio.run(evaluator.run_all())
    print_eval_report(results)

    # 3. Export report for CI comparison
    output_path = project_root / "eval_report.json"
    report = {
        "timestamp": "2026-06-09",
        "prompt_coverage": {
            k: {
                "met": sum(1 for v in vv.values() if v),
                "total": len(vv),
                "items": vv,
            }
            for k, vv in coverage.items()
        },
        "mock_eval_results": [
            {"id": r["scenario_id"], "name": r["name"],
             "score": r["score_pct"], "grade": r["grade"]}
            for r in results
        ],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  Report saved to: {output_path}")


if __name__ == "__main__":
    main()
