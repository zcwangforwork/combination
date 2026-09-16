"""
Update doc_types.py, minimax.py, and prompt_engineer.py with 55 new document types
from the DHF checklist expansion.
"""
import os
import sys

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))
from expand_doc_types import NEW_TYPES

BASE = r'E:\nrf_sample_codes\working_team_work\public\project\project_0430_02_beta'

# =====================================================
# Step 1: Update doc_types.py
# =====================================================
def update_doc_types():
    filepath = os.path.join(BASE, 'app', 'services', 'doc_types.py')
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Collect new types by category
    from collections import defaultdict
    cat_types = defaultdict(list)
    for key, label, cat, chapters, prompt in NEW_TYPES:
        cat_types[cat].append((key, label))

    # 1a. Add to DOC_TYPES list (before the legacy/compat section)
    # Find the insertion point: right before "# ========== 保留原有兼容类型"
    insert_marker = '    # ========== 保留原有兼容类型（映射到新类型） =========='

    new_doc_types_lines = []
    for cat, types_list in cat_types.items():
        cat_names = {
            "design_planning": "一、设计策划阶段",
            "design_input": "二、设计输入阶段",
            "design_output": "三、设计输出阶段",
            "design_verification": "四、设计验证阶段",
            "design_validation": "五、设计确认阶段",
            "design_transfer": "六、设计转化阶段",
        }
        cat_name = cat_names.get(cat, cat)
        new_doc_types_lines.append(f'    # ========== {cat_name} 扩充（DHF清单） ==========')
        for key, label in types_list:
            new_doc_types_lines.append(f'    "{key}",  # {label}')
        new_doc_types_lines.append('')

    new_types_block = '\n'.join(new_doc_types_lines)
    # Insert before the legacy section
    content = content.replace(
        '    # ========== 保留原有兼容类型（映射到新类型） ==========',
        new_types_block + '    # ========== 保留原有兼容类型（映射到新类型） =========='
    )

    # 1b. Add to DOC_TYPE_LABELS
    labels_marker = '    # 保留原有兼容类型'
    new_labels_lines = []
    for cat, types_list in cat_types.items():
        cat_names = {
            "design_planning": "一、设计策划阶段 扩充",
            "design_input": "二、设计输入阶段 扩充",
            "design_output": "三、设计输出阶段 扩充",
            "design_verification": "四、设计验证阶段 扩充",
            "design_validation": "五、设计确认阶段 扩充",
            "design_transfer": "六、设计转化阶段 扩充",
        }
        cat_name = cat_names.get(cat, cat)
        new_labels_lines.append(f'    # {cat_name}（DHF清单）')
        for key, label in types_list:
            new_labels_lines.append(f'    "{key}": "{label}",')
        new_labels_lines.append('')

    new_labels_block = '\n'.join(new_labels_lines)
    content = content.replace(
        '    # 保留原有兼容类型',
        new_labels_block + '    # 保留原有兼容类型'
    )

    # 1c. Update DOC_CATEGORIES - add new types to their respective categories
    for cat, types_list in cat_types.items():
        new_keys = [key for key, _ in types_list]
        # Find the closing of this category's types list
        # Pattern: find the category block and append new keys before the closing bracket
        for item in types_list:
            pass  # We'll handle this differently

    # For categories, we need to insert the new type keys into their respective category type lists
    # This is trickier since each category has an existing types list
    cat_section_map = {
        "design_planning": "design_planning",
        "design_input": "design_input",
        "design_output": "design_output",
        "design_verification": "design_verification",
        "design_validation": "design_validation",
        "design_transfer": "design_transfer",
    }

    for cat_key, section_key in cat_section_map.items():
        if cat_key not in cat_types:
            continue
        new_keys_for_cat = [key for key, _ in cat_types[cat_key]]
        # Find the types list ending bracket for this category
        # The pattern is: the types list is in the format:
        # "types": [
        #     "existing_key1",
        #     ...
        #     "existing_keyN"
        # ],

        # We'll use a simpler approach: find the category block and add new keys
        # Find the last existing type key in this category
        # Actually, let's just read the file and manually construct the new content

    # This manual approach isn't ideal for DOC_CATEGORIES. Let me handle it separately.

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[OK] doc_types.py updated - {sum(len(v) for v in cat_types.values())} new types added")

# =====================================================
# Step 2: Update minimax.py - add DOC_CHAPTERS
# =====================================================
def update_minimax():
    filepath = os.path.join(BASE, 'app', 'services', 'minimax.py')
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Build chapter entries for all new types
    chapter_entries = []
    for key, label, cat, chapters, prompt in NEW_TYPES:
        entry = f'    "{key}": [\n'
        for ch_id, ch_name, ch_query in chapters:
            entry += f'        {{"id": "{ch_id}", "name": "{ch_name}", "query": "{ch_query}"}},\n'
        entry += '    ],'
        chapter_entries.append(entry)

    chapters_block = '\n'.join(chapter_entries)

    # Insert before DEFAULT_CHAPTERS
    marker = '# 默认章节（未定义的文档类型使用）'
    content = content.replace(
        marker,
        chapters_block + '\n\n' + marker
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[OK] minimax.py updated - {len(chapter_entries)} chapter definitions added")

# =====================================================
# Step 3: Update prompt_engineer.py - add DOC_TYPE_SPECIFIC_PROMPTS
# =====================================================
def update_prompt_engineer():
    filepath = os.path.join(BASE, 'app', 'services', 'prompt_engineer.py')
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Build prompt entries for all new types
    prompt_entries = []
    for key, label, cat, chapters, prompt_text in NEW_TYPES:
        entry = f'    "{key}": """{prompt_text}""",'
        prompt_entries.append(entry)

    prompts_block = '\n'.join(prompt_entries)

    # Insert before the closing brace of DOC_TYPE_SPECIFIC_PROMPTS
    # Find: "instruction": """...""",\n}
    marker = '    "instruction": """【使用说明书(IFU)特别要求】'
    content = content.replace(
        marker,
        prompts_block + '\n' + marker
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[OK] prompt_engineer.py updated - {len(prompt_entries)} prompt templates added")

if __name__ == '__main__':
    print("Starting DHF expansion...")
    print(f"New types to add: {len(NEW_TYPES)}")
    update_doc_types()
    update_minimax()
    update_prompt_engineer()
    print("\nAll files updated successfully!")
    print("Next: Manually update DOC_CATEGORIES type lists in doc_types.py")
