# 独立的 RHF Hessian、IR 和 Raman 对照

VeloxChem CPU 与 n2 上官方 GPU4PySCF 1.9.2 分别从几何和基组执行全 FP64、直接四中心的 RHF。两侧读取相同的原子顺序、Bohr 坐标、STO-3G 指数和收缩系数。SCF 及响应参数设为 1e-10，各实现沿用其原生收敛范数。比较器将 Hessian 按 atom×xyz 排序，以 Eh/Bohr² 逐分量验收。水的质量为 O 15.999、H 1.008 amu，比较静态非共振 Raman 和投影掉平动/转动的三个模式。[输入与阈值](protocol.json)

| 分子 | 核坐标 RHS 数 | Hessian 分量 | 最大绝对差（Eh/Bohr²） |
|---|---:|---:|---:|
| H₂O | 9 | 81 | 3.72421e-8 |
| NH₃ | 12 | 144 | 3.66266e-9 |
| LiH | 6 | 36 | 7.17447e-9 |

RHS 数按 3N 计算。两个后端各自产生三份完整矩阵，261 对元素全部通过 1e-7 的门槛。三个体系的最大能量差为 9.81e-13 Hartree。水的一个模式为虚频，约 1980.57i cm⁻¹。该固定几何的曲率与光谱读数保留虚频符号。频率最大差 0.000307 cm⁻¹，IR 强度最大差 1.33e-5 km/mol。[逐项评分](verification.json)

水的默认 Raman 活性通过 0.05 Å⁴/amu 的阈值，但三个去偏振比全部超过 0.005，最大差为 0.01630。GPU4PySCF 的默认路径对外电场求梯度的二阶差分，VeloxChem 使用解析极化率导数。精修用已验收的质量归一化模式位移几何，以两个预先写下的步长从静态极化率重算。额外 12 个正负位移各用 1 次 SCF 和 3 个电场 RHS，共 17.06 秒。细步长的去偏振比与 VeloxChem 最大差 3.30e-7，活性最大差 9.80e-4 Å⁴/amu，粗细步长也通过原门槛。发布时保留原三次拒绝和精修费用。[精修约定](raman-refinement.json) · [位移、时间和原始张量](raman-refinement/displacements.jsonl)

VeloxChem 包的构建配方精确指向提交 `8513267a275d8f3feca17e9d24741ceeaedaa6b6`。发行包版本号为 1.0，模块自报 1.0rc4。全树核对了 6,868 个文件，源码覆盖表逐文件记录索引、局部审读、行为追踪和执行状态。此处的 VeloxChem 结果来自单 MPI rank、两线程 CPU。GPU CPKS 性能和异构样本端到端成本仍需各自实测。[源码锁与实验记录](veloxchem/source-lock.json) · [全树覆盖](veloxchem/source-coverage.csv.gz)

## 复验

从仓库根目录运行以下命令。数值复核只需 Python 标准库。原始执行日志以 gzip 保存，SHA-256 在源码锁中。首次 CPU 运行在导出 AO 数时失败，初次三条失败与后续独立重算分别计费。

```bash
e=handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/cross-engine
python3 scripts/verify_cross_engine_hessians.py --root "$e" --out /tmp/cross-engine-score.json
pixi install --locked --manifest-path "$e/veloxchem/pixi.toml"
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 pixi run --manifest-path "$e/veloxchem/pixi.toml" \
    python scripts/run_cross_engine_hessians.py veloxchem --protocol "$e/protocol.json" --out /tmp/velox-rerun
```

GPU 侧将 `protocol.json` 和两个生产脚本放入新运行目录，在已分配的单 GPU 上执行 `gpu.slurm`。将其输出目录作为 `refine.slurm` 的第一个参数并提供 `raman-refinement.json`。GPU4PySCF 的 wheel 身份和版本环境见此前已运行的[匹配环境回执](../../../environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/v1.9.2-wheel-test-receipt.json)。
