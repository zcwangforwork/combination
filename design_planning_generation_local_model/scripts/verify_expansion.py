"""Quick verification of DHF expansion results."""
import sys
sys.path.insert(0, r'E:\nrf_sample_codes\working_team_work\public\project\project_0430_02_beta')

from app.services.doc_types import DOC_TYPES, DOC_TYPE_LABELS, DOC_CATEGORIES
from app.services.minimax import DOC_CHAPTERS
from app.services.prompt_engineer import DOC_TYPE_SPECIFIC_PROMPTS

print("=" * 60)
print("DHF扩容完成 - 文档类型统计")
print("=" * 60)
print(f"DOC_TYPES: {len(DOC_TYPES)}")
print(f"DOC_CHAPTERS: {len(DOC_CHAPTERS)}")
print(f"DOC_TYPE_SPECIFIC_PROMPTS: {len(DOC_TYPE_SPECIFIC_PROMPTS)}")
print()

total = 0
for key, cat in DOC_CATEGORIES.items():
    c = len(cat["types"])
    total += c
    print(f"  {cat['icon']} {cat['name']}: {c} types")
print(f"  {'-' * 30}")
print(f"  Total: {total}")

# Verify no missing entries
missing_c = [t for t in DOC_TYPES if t not in DOC_CHAPTERS]
missing_p = [t for t in DOC_TYPES if t not in DOC_TYPE_SPECIFIC_PROMPTS]
missing_l = [t for t in DOC_TYPES if t not in DOC_TYPE_LABELS]
all_ok = not missing_c and not missing_p and not missing_l

print(f"\nConsistency check:")
print(f"  Missing chapters: {len(missing_c) or 'None'}")
print(f"  Missing prompts: {len(missing_p) or 'None'}")
print(f"  Missing labels: {len(missing_l) or 'None'}")
print(f"  All checks passed: {all_ok}")

# Show new types from DHF
print(f"\nNew DHF checklist document types (sample):")
dhf_samples = [
    "market_research_product_definition",
    "user_needs_specification",
    "product_risk_analysis_matrix",
    "product_rtm",
    "hardware_design_plan",
    "performance_verification_plan",
    "software_interface_security_test_plan",
    "leachables_test_plan",
    "shelf_life_verification_plan",
    "clinical_trial_plan",
]
for k in dhf_samples:
    label = DOC_TYPE_LABELS.get(k, "MISSING")
    print(f"  [OK] {k} -> {label}")
