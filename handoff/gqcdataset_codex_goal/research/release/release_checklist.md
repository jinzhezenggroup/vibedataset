# 可复现发布包与 claim gate（Issue #42）

机器可读发布清单是 `release_manifest.json`，主张表是 `claims.csv`。`git_head` 指向被审计的 source commit，`built_from_git_head` 记录生成该快照时的 checkout。CI 还会在当前 checkout 临时重建 release manifest，并用 strict-head 检查当前 HEAD 与新 manifest 一致。每条主张绑定固定 artifact SHA、条件和未知成本。官方 GPU4PySCF 1.9.2 wheel 的选定上游测试已通过，但完整上游 suite、1.9.0 可执行环境和论文版本映射仍保持 unknown。10× 仍写成 `falsified-partial`，没有把未知 telemetry 填成零。

发布前必须补齐清单中的 unknowns，或按 claims.csv 的 partial/falsified 状态发布。
