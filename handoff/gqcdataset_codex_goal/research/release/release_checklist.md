# 可复现发布包与 claim gate（Issue #42）

机器可读发布清单是 `release_manifest.json`，主张表是 `claims.csv`。每条主张绑定固定 artifact SHA、条件和未知成本。当前包把 10× 写成 `falsified-partial`，没有把未知 telemetry 填成零。

发布前必须补齐清单中的 unknowns，或按 claims.csv 的 partial/falsified 状态发布。
