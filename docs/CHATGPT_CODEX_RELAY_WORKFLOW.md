# ChatGPT 网页与 Codex 的中继开发流程

这份手册适合由一个人同时使用 ChatGPT 网页和 Codex。ChatGPT 网页负责提出问题、审核证据和决定是否继续。Codex 负责读取仓库、修改代码、运行验证、提交和创建 pull request。用户负责在两个界面之间传递结构化信息。

## 角色边界

| 角色 | 工作内容 | 交付物 |
|---|---|---|
| ChatGPT 网页 | 把研究问题变成 issue，检查科学身份、竞争解释、失败边界和 PR 证据 | issue 文本、审查意见、合并决定 |
| Codex | 读取 `AGENTS.md`，建立分支和 worktree，修改实现，运行检查，提交并推送 | commit、PR、测试回执、限制和后续 issue |
| 用户 | 传递 issue 和审查意见，不在聊天中传递凭据 | 结构化消息 |

当前仓库的默认分支规则要求 pull request、禁止强推和删除、只允许 squash，并要求 `Response validation gate`。merge queue 会重新运行同一套检查。

## 一轮工作的完整顺序

### 1. 先让 ChatGPT 网页写 issue

把研究问题交给 ChatGPT 网页时，要求它输出以下字段：

```text
仓库：jinzhezenggroup/vibedataset
问题：
目标科学身份：
输入和固定版本：
允许修改的范围：
竞争解释：
必须记录的失败：
验收命令：
预期产物：
停止条件：
```

ChatGPT 网页只在问题、依赖和验收条件足够明确时给出“可以执行”。它应当保留负结果和证据不可得状态。

### 2. 把 issue 原文传给 Codex

向 Codex 发送一条完整消息，不要只转发一句“实现这个”：

```text
请执行 GitHub issue #<数字>。

仓库：jinzhezenggroup/vibedataset
基线：main
目标分支：codex/<issue>-<短名称>
问题：<issue 原文>
验收条件：<逐条复制>
限制：<方法、基组、状态、单位、权限、不可修改范围>
资源：<本地环境、n2/n5、固定源码、是否允许网络获取>
完成标准：运行验证、提交 commit、推送分支、创建 PR，并返回证据摘要。
```

Codex 的正常入口是读取根目录 `AGENTS.md`、当前状态和 issue 导航，然后检查工作区，再创建隔离分支。它不应覆盖工作区中其他人的未提交改动。

### 3. Codex 执行和提交 PR

Codex 应该返回以下固定格式：

```text
分支：
基线：
commit：
PR：

实现：
验证命令：
验证结果：
CI 状态：
科学身份：
失败和证据不可得：
新增或保留的资产：
未完成事项：
```

当前仓库的本地检查入口如下：

```bash
python3 scripts/check_response_ci.py archive --out .work/response-archive-<日期>
.work/response-science-env/bin/python scripts/check_response_ci.py science --out .work/response-science-<日期>
/home/lhshen/.local/bin/uv tool run --from pre-commit==4.0.1 pre-commit run --all-files --show-diff-on-failure
```

PR 描述需要填写科学身份、独立参照、失败路径、成本、持久资产和负结果。CI 通过后，Codex 不应把“脚本退出 0”扩展成更宽的科学结论。

### 4. 把 Codex 回执传回 ChatGPT 网页

传递最小但完整的审核包：

```text
请审核这个 PR：

PR 链接：
base/head：
本次目标：
改动文件：
commit：
CI 检查：
本地命令和结果：
独立参照：
失败、拒绝和 evidence_unavailable：
成本和存储：
请检查科学身份、实现行为、测试覆盖、证据完整性和是否需要新增 issue。
```

ChatGPT 网页审核时，以 GitHub PR 的实际 diff、评论和 checks 为准。它应逐项回答：

1. 目标问题是否仍与实现一致。
2. 方法、基组、几何、电子数、自旋、状态、单位、AO/MO 约定和性质定义是否完整。
3. 旧资产是直接可复用、初猜、需要精修、拒绝还是必须重算。
4. 验证是否包含独立参照、失败样本、成本和负结果。
5. 是否存在把残差、缓存、热启动、RHS 数量或接口存在误写成科学结论的情况。
6. 是否可以合并，或者需要给 Codex 一个具体修改任务。

如果 ChatGPT 的 GitHub Code Review 已连接到仓库，可以在 PR 中使用 `@codex review` 请求 Codex 发布标准 review。Code Review 会读取 PR diff、仓库指导和 `AGENTS.md`。网页审核仍应保留人的科学判断。

### 5. 反馈和返工

需要修改时，ChatGPT 网页输出：

```text
PR：
结论：changes requested
必须修改：
1. 文件、符号、问题和验收方式
2. 文件、符号、问题和验收方式
保留内容：
禁止扩大范围：
重新运行：
```

用户把这段原文传给 Codex。Codex 只修改本轮范围，重新运行受影响检查，并在同一个 PR 推送新 commit。不要为每个小意见创建新的 PR。

### 6. 合并

当前规则集启用 merge queue。检查全部通过后，使用：

```bash
gh pr merge <PR号> --repo jinzhezenggroup/vibedataset --auto
```

队列模式下不要手动指定 `--squash`。规则集会使用 squash 策略。合并后检查：

```bash
gh pr view <PR号> --repo jinzhezenggroup/vibedataset
gh run list --repo jinzhezenggroup/vibedataset --branch main --limit 5
gh api repos/jinzhezenggroup/vibedataset/contents/.github/workflows/response.yml?ref=main
```

当前强制批准数为 0，所以一个 GitHub 账号可以完成开发和合并。PR 作者不能给自己的 PR 提交有效批准。需要独立批准时，再添加第二个账号、配置 `.github/CODEOWNERS`，并把规则集的批准数改为 1。

## 每日最短操作模板

### ChatGPT 网页发给 Codex

```text
执行 issue #<数字>。请先读取仓库规则和当前状态，再建立隔离分支。完成 issue 中的实现和验收，运行 archive/science tier，推送分支并创建 PR。返回 commit、PR、命令、结果、失败和剩余问题。
```

### Codex 发回 ChatGPT 网页

```text
Issue #<数字> 已执行。
PR：<链接>
commit：<SHA>
改动：<摘要>
验证：<命令和结果>
CI：<状态>
限制：<失败、负结果、证据不可得>
请按科学身份、独立参照、失败边界和成本审核。
```

### ChatGPT 网页发回 Codex

```text
PR #<数字> 审核结论：<approve / changes requested>
必须处理：
- ...
重新验证：
- ...
保持：
- ...
```

## 需要升级资源时

- **第二个 GitHub 账号**：只有要强制独立批准时需要。不要在聊天中传密码或 token。
- **GPU runner**：当前 PR 门禁使用 Ubuntu CPU runner。n2/n5 用于 GPU 和 Slurm 研究证据。
- **私有数据或源码**：先建立许可证和来源记录，再通过 issue 申请只读 secret。不要把凭据写进仓库。
- **大日志和 profiling**：保留压缩后的可审查摘要，原始临时文件放在 `.work/` 或 CI artifact。

## 出错时的处理

- CI 失败时，Codex 先读取 job 日志并修复可复现原因。ChatGPT 网页只审核修复后的证据。
- 科学门槛失败时，保留失败记录和分母，不通过放宽阈值凑合格率。
- PR 冲突时，Codex 把最新 `origin/main` 合入工作分支，重新运行全部检查，再推送。
- 需要改变科学定义时，先让 ChatGPT 网页开新 issue，再让 Codex 执行。不要在原 PR 中悄悄改变目标。
- 发现当前分支有未提交文件时，先记录文件归属，使用独立 worktree，避免覆盖已有工作。

## 与 GenerativeQC 的对应关系

```text
issue 定义
  → 隔离分支和小 PR
  → 本地 hooks 和独立科学检查
  → PR diff 与证据审核
  → merge queue 重新验证
  → squash 到 main
  → issue 关闭并留下结果、负结果和后续 issue
```

这个流程让 ChatGPT 网页承担审查和决策，Codex 承担可执行工程工作。两边传递 commit、PR、命令和证据，不传递凭据，也不把聊天中的意图当成已完成的代码。

## 官方产品说明

- [Review GitHub pull requests with Codex](https://learn.chatgpt.com/docs/third-party/github)
- [Code review](https://learn.chatgpt.com/docs/code-review)
- [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action)
