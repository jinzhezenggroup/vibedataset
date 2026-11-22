# 三个分子的共享振动响应

固定核几何、STO-3G 的实际基函数、核质量、场原点和 FP64 容差。水、氨和氢化锂各请求 Hessian、IR 和静态 Raman，共 12 次性质请求，三种请求密度。VeloxChem 1.0rc4 的 CPU 进程独立计算了三个分子的完整 Hessian 与谱。n2 作业 5657 在同一张 RTX PRO 6000、同一 GPU4PySCF 1.9.2 wheel 上分别运行逐请求和共享执行。共享对象限于完全相同的分子 SCF 态。Hessian 与 IR 通过私有驱动复用同一批 3N 笛卡尔响应，每次缓存查找核对轨道、H1、原子列表和响应算子身份。

| 实测工作 | 逐请求 | 共享 |
|---|---:|---:|
| 原始 SCF | 12 | 3 |
| 几何 CPHF 求解 | 16 | 3 |
| 几何 CPHF RHS | 144 | 27 |
| 原始进程墙时，s | 111.17 | 66.98 |
| 默认读出通过数 | 8/12 | 8/12 |
| Raman 纠正的位移 SCF | 44 | 40 |
| 纠正的电场 RHS | 132 | 120 |
| 纠正程序中实测的位移循环，s | 100.74 | 100.99 |
| 通过原容差的最终请求 | 12/12 | 12/12 |

水和氨的默认去偏振比、氢化锂两次请求的默认 Raman 活性被独立评分拒绝。作业 5662 和 5665 分别执行共享和逐请求的纠正。固定步长为 0.001 和 0.0005 Bohr√amu。两档结果都通过不变的活性和去偏振比阈值。最终发布数值从较细步长读取，原始失败值保留在默认回执中。端到端比较须计入纠正、独立验证和发布的实际成本。[原始默认结果](default-verification.json) · [带数值、误差和回退的发布记录](verification.json)

水和氨分别有 −1980.57 和 −1457.42 cm⁻¹ 的带符号振动频率，极小点谱的频率门拒绝这两个几何。氨还包含两对相距不足 5 cm⁻¹ 的模式。另以固定受限对称态的伸长 H₂ 实测 0.000500 Eh 轨道间隙，触发 0.001 Eh 门。强制 SCF 不收敛、私有 allocator 的真实 OOM、不支持性质分别留下请求级拒绝；对照的正常水 Hessian 通过 VeloxChem 核验。完整结果使用的字节数单列在验证文件。跨设备、其他泛函和不同请求分布各需匹配的计算。[协议与队列](protocol.json)

复核使用 Python 标准库。

```bash
d=handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/shared-spectroscopy
python3 scripts/score_shared_spectroscopy.py --root "$d" --protocol "$d/protocol.json" \
  --refinement "$d/shared-refinement" --serial-refinement "$d/serial-refinement" --out /tmp/shared-spectroscopy.json
```

单独的作业 5687 封存了另一遍共享执行中真正使用的 H1、轨道系数、占据、轨道能、27 个 Cartesian MO1 和占据块能量导数。独立 CPU PySCF 用 AO J/K 与核坐标重叠导数验证未预条件的虚占轨道方程、占据轨道正交约束及占据块能量导数。三份物理状态各自通过，12 个请求都绑定到对应的解散列。对一个响应振幅加入 0.01 的损坏控制后，未预条件残差为 0.204。此验证单列测量成本。[原始张量和独立残差](cartesian-certificate/independent.json)
