# 可复现发布包与 claim gate（Issue #42）

CI 的 attribution artifact 提供当前提交的 release_manifest.json、claims.csv 和对应原始文件。git_head 绑定打包时的 Git 提交，audited_baseline_git_head 记录最初受控实验的提交。验证器逐文件核对 Git blob 和 SHA-256。仓库内历史快照按清单记录的提交重放。
