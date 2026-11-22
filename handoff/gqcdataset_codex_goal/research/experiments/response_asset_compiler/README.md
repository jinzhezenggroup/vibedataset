# Response asset compiler（Issue #39）

`scripts/compile_response_assets.py` 把几何、method、basis、charge、multiplicity、AO 表示、原点、单位和精度绑定成 source/target identity。相同身份输出 `direct_reuse`，方法/基组变化输出 `refine_required`，状态身份变化输出 `reject-and-recompute`。计划生成不加载 oracle 或 scorer。

固定计划包含 17 个同协议 direct reuse、2 个 refine-required 和 1 个开放壳层 reject。每行把质量证书标为 `independent_scorer_required` 或 `evidence_unavailable`，不能把残差估计冒充独立证据。`verify_response_asset_compiler.py` 检查身份、分母和 truth-leakage flags。

它是 #38 PreparedPropertyBatch 的身份/资产入口。真正把 density、DF/JK、响应向量编译成 GPU resident 程序，需要 #37 的 profile 和 #40 的 Hessian/CPKS 主负载。

`gpu-assets.json` 将官方 GPU4PySCF C 臂的 51 条 request receipt 编译为 identity-bound GPU response assets，保留 response vectors、AO response densities、target、源 receipt hash 和独立 scorer certificate。`gpu-assets-verification.json` 独立检查 manifest/geometry identity、字段覆盖、asset SHA 和 51/51 scorer accepted，结果为 passed。该步骤复用已封存 C receipt，不重新运行 CPHF，producer 也没有加载 scorer。

这组 51 个 direct assets 只覆盖同一 RHF/STO-3G 协议。跨方法/基组 refine、开放壳层 reject、损坏/过期资产和完整 response certificate frontier 仍由计划文件保留为未完成边界。

`gpu-assets-negative-controls.json` 还保留了三种 verifier 负对照。陈旧 asset hash、错误 geometry identity 和缺失 response density 均得到 `reject-and-recompute`，没有把损坏资产静默接受。

## 官方 1.9.2 四臂的 AO 质量证书

独立 CPU PySCF 从 17 份几何重建 RHF/sto-3g、三方向的稠密响应及最小奇异值。输入包括四臂新测的 AO 一阶密度与读出。在 CPU 的占据/虚轨道基底中，候选响应为 `Cᵥᵀ S D¹ S Cₒ / 2`。评分器从投影结果重新产生密度，调用 AO J/K 计算未预条件化的候选残差，并同时检查稠密参照、AO 切空间和目标读出。早先独立 MO 实现中有 30 行 operator-image 诊断值超限；这 30 行均纳入本次独立计算。

204/204 行通过 1e-5 的绝对门槛，最大候选物理残差 4.45832e-6，稠密参照最大残差 L2 为 3.59e-15。此证书覆盖 AO 密度与标量。原生产轨道基底下的裸 MO 向量仍受其原始参考态约束。截断、NaN、数值错误但有限的密度、错读出、错单位、错场 RHS 六个试验均被拒绝。另对 51 个存档 C 资产运行真实发布校验器，14 个存储层负对照均被拒绝，其中包括重新计算自有哈希后的错基组、陈旧残差和被替换密度。CPU 未读取 GPU scorer 的预先判断。[逐行计算、计时与负对照](scorer-v192-ao.json.gz) · [发布校验结果](gpu-assets-negative-controls.json)

从仓库根目录运行以下命令，使用与科学 CI 相同的 PySCF 2.14.0 环境。

```bash
r=handoff/gqcdataset_codex_goal/research
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python scripts/score_ao_density_response.py \
    --manifest "$r/experiments/attribution_4arm/manifest.json" \
    --raw-root "$r/environment/gpu4pyscf-20261122/a-d-telemetry/raw" --out /tmp/independent-ao-score.json.gz
```

## 跨基组、方法和几何的实测

n2 作业 5644 比较了普通求解与资产规划，每路 15 个请求。三份同协议 AO 响应经目标残差复核后直接复用。甲烷、氨和水转换至 6-31G* 或 B3LYP 后，用同几何 AO 重叠投影作为官方 CPHF 的初值，实际执行了六次目标求解。位移几何、改变原点、陈旧文件、错场方向及冻结密度触发五次实际冷重算。开放壳层各保留一条缺少受限解的处置。新 CPU PySCF 在每个目标收敛独立 SCF，逐列构建全空间响应矩阵，并核对 AO 密度、逐分量读出与未预条件物理残差。可评分的 28/28 通过。

固定 fresh cache 和进程边界的作业 5647 再以 cold/planned 与 planned/cold 各跑一轮。两轮中每种路径各有 14 个合格结果和一个保留的开放壳层缺口。规划的 CPHF solver operator rows 从 194 降至 174，质量检查另外付费。四个完整进程的全部墙时、压缩字节和独立评分一并保留。运行范围为三个中性小分子，规模证据按其独立合同验收。[原始记录与摘要](frontier/summary.json)
