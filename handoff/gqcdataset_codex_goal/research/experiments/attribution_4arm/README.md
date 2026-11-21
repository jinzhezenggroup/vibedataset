# 四臂归因与目标相关 planner（Issues #31、#33）

核对日期：2026-11-22。实验使用同一封存 manifest、17 个 QM9 几何和三条请求轨迹。每个分子按 `cycle-one → cycle-three → cross-three` 顺序处理。A–D 在 n2 的 NVIDIA RTX PRO 6000 Blackwell GPU 上分别启动，生产进程没有读取 oracle 或 scorer。

## 四臂定义

| 臂 | 编排 | 后端 | 结果文件 |
|---|---|---|---|
| A | native-ordinary，每条请求都重新求所需字段 | 官方 GPU4PySCF | `raw/raw-A.jsonl`、`runs/run-A.json` |
| B | native-ordinary | 同一官方版本加 `response-cache` patch | `raw/raw-B.jsonl`、`runs/run-B.json` |
| C | `gqc-planner-assets`，同协议资产按字段身份复用 | 官方 GPU4PySCF | `raw/raw-C.jsonl`、`runs/run-C.json` |
| D | 同 C | 同一份 patch | `raw/raw-D.jsonl`、`runs/run-D.json` |

官方 GPU4PySCF commit 是 `5a717f899cb40d64a5799ef1df7e3626c505c3bd`。patch 只增加显式传入的 exact FP64 operator-image cache，完整输入字节不相同时仍调用原始 `fvind`。它不改变 SCF/CPHF 方程、容差或参考态。B/D 的 run JSON 保留实际运行时 patch SHA，并另列当前可 apply/reverse 的 `patch_sha256_replayable`。两者生成相同的 patched source SHA。缓存命中和未命中都记录在每条响应记录的累计快照内。

`scripts/test_gpu4pyscf_patch_contract.py` 在固定源码副本上实际 apply 和 reverse patch，并检查 `backend_cache` 与 `ResponseOperatorCache` 的入口。`patch-contract.json` 保存了原始、patched 和 patch SHA-256。

生产命令使用以下形态。A/C 的 `PYTHONPATH` 为空，B/D 指向保留官方编译扩展的 patched site-package 副本。

```bash
$GQC_PYTHON scripts/run_gpu4pyscf_4arm.py \
  --manifest attribution_4arm/manifest.json --arm A --out raw-A \
  --source-commit <project-commit> \
  --gpu4pyscf-source-commit 5a717f899cb40d64a5799ef1df7e3626c505c3bd
```

## 独立评分

`scripts/score_gpu4pyscf_4arm.py` 在新的 n2 进程中只加载官方 GPU4PySCF。它重新构造每个分子的 SCF 和三列响应，检查目标标量、独立残差和 AO 密度响应。MO 响应向量还保留逐项差异作为轨道相位诊断。接受门槛为目标和 AO 密度误差 `5×10⁻⁵`，独立残差 `1×10⁻⁵`。这组门槛在评分前固定，生产记录中的误差字段不作为真值。

`score.json` 的 204 条记录全部通过，四臂各为 51/51。四臂最大目标误差分别为 A `3.73×10⁻⁶`、B `3.73×10⁻⁶`、C `4.27×10⁻⁶`、D `4.27×10⁻⁶`。独立 oracle 残差最大为 `1.06×10⁻⁶`。AO 密度最大差异为 `3.32×10⁻⁵`。MO 逐项差异不作为物理失败，因为不同进程的 SCF 轨道相位可以不同。

## 成本与主效应

`summary.json` 从四份原始 JSON 逐项重建配对统计，包含中位数、几何均值和确定种子的 bootstrap paired 95% 区间。17 个分子与三条轨迹的汇总如下。

| 臂 | RHS 列 | 响应 operator rows | 质量 operator rows | response seconds | molecule seconds | cache 最终快照 |
|---|---:|---:|---:|---:|---:|---|
| A | 102 | 677 | 102 | 113.40 | 408.16 | 无 |
| B | 102 | 643 | 102 | 201.60 | 558.71 | 47 calls，2 hits，45 misses |
| C | 51 | 352 | 51 | 76.71 | 367.47 | 无 |
| D | 51 | 352 | 51 | 108.12 | 428.89 | 24 calls，0 hits，24 misses |

相对于 A，C 将 RHS 列和 operator rows 减半附近，几何均值的 operator-row 比为 `0.833`，端到端 molecule time 的几何均值比为 `0.915`。C 的 response seconds 配对中位数差为 `+0.0023 s`，95% 区间跨过零。B 的缓存没有产生端到端收益，native molecule time 几何均值比为 `1.283`。D 相对于 C 的几何均值比为 `1.141`。交互项 `(D−B)−(C−A)` 的 molecule-time 配对中位数为 `−1.254 s`，95% 区间为 `[-2.375, -0.353]`。这里的负交互来自 B 的 patch 开销，不能写成普遍后端加速。

`operator_rows` 是 GPU CPHF induced-potential map 的实际输入行数。它不是未经测量的 J/K 猜测。每条记录另外保存 SCF cycle、host/device 字节、响应时间、质量核验行数和完整墙时。

## 失败和扩展协议

`negative-controls.json` 逐项保留错误基组复用、近奇异残差界和 multiplicity mismatch。三项均为 `reject-and-recompute`。近奇异控制的条件数为 `10¹²`，残差 `10⁻⁸` 给出的严格离散界为 `10⁴`，目标容差为 `10⁻⁶`。

`expansion.json` 在同一 GPU 环境中记录更大基组 `RHF/6-31G*`、`B3LYP/STO-3G` 和带电开放壳层 `UHF/STO-3G`。更大基组的 RHF 直接响应完成。RKS 与 UHF 的当前 GPU4PySCF 极化率入口是 restricted-RHF-only，四臂均保留 `reject-and-recompute` 记录。C/D 对更大基组标记 `refine-required`，没有把 STO-3G 资产直接当成新协议响应。

## Issue #33 planner

`scripts/target_response_planner.py` 只读取 manifest 和四臂 raw 成本。它预登记短队列、混合目标和近似全覆盖三种请求分布，以及未来请求概率 `0.2/0.5/0.9`。候选包括 native field、GQC asset、vector precompute、dense prefetch 和 reject-and-recompute。目标函数同时收取历史/未来计算、operator rows、传输、存储和风险项。

规划器生成 564 个决策和 765 个 in-domain 候选，包含 17 个实测分子、三种分布、三个概率、111 个几何/方法/状态 OOD 决策，以及来自固定 QHNet/RMD17 目录的 100 个外部几何 inventory 案例。几何拉伸和压缩两种变体均标记为 `refine-required`。外部 inventory 只用于 planner 的协议拒绝计数，没有响应标签或物理评分。基组、方法和 multiplicity 改变标记为 `reject-and-recompute`。`verify_target_response_planner.py` 不加载 scorer，重算全部目标函数并检查选择一致性，结果为 `passed`。规划器输出的 `oracle_loaded` 和 `scorer_loaded` 均为 false。

该 planner 产出的是可审计的 cost–coverage–risk frontier。四臂物理质量结果仍由 `score.json` 独立给出，不能用 planner 的成本模型替代响应级科学验证。
