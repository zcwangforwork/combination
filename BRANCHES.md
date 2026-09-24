# 分支开发工作流（git worktree）

本仓库用 `git worktree` 实现"每分支一个独立目录、共享同一仓库"的并行开发模式。

## 目录布局

```
E:\A_nrf_sample_codes\working_team_work\public\project\git_project\
├── combination\          ← 主分支 main（稳定版，对外运行）
├── combination-dev\      ← 开发分支 dev（本目录）
└── combination-dev-xxx\  ← 其他开发分支（按需创建）
```

## 常用操作

```bash
# 开新分支目录（在任意本仓库目录执行）
git worktree add ../combination-dev-xxx -b dev-xxx

# 查看所有分支目录
git worktree list

# 改完代码：在分支目录提交
git add -A
git commit -m "改动说明"

# 合并回主分支（回主目录执行）
cd ../combination
git merge dev-xxx

# 分支用完清理
git worktree remove ../combination-dev-xxx   # 删目录
git branch -d dev-xxx                         # 删分支
```

## 注意事项

1. **同一分支只能检出于一个目录**：main 只在主目录，每个分支目录检出自已的分支
2. **新分支目录不含被 .gitignore 排除的文件**：`.env` 需手工复制（本目录已复制）；
   `node_modules`/`chroma_db*`/`project_store`/`downloads` 等运行时数据需按需复制或重建
3. **merge 冲突**：两个分支改了同一处代码时，merge 会标出冲突位置，
   手工取舍后 `git add <文件>` + `git commit` 完成合并
4. **主目录保持干净**：merge 前主目录如有未提交改动，先提交或 `git stash`
5. 在分支目录启动后端服务前确认 `.env` 已复制；两个目录的服务不要同时用同一个端口
