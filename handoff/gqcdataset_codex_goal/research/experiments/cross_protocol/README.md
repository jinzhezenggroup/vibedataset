# Issue #18 跨协议资产可迁移边界

本轮用同一几何的小规模协议矩阵检验“资产字段可读”是否等于“科学目标可复用”。
[协议](protocol.md) · [逐项结果](result.json) · [离线核验](verify.py)

## 结果矩阵

| 来源资产 | 目标协议 | 分类 | 独立证据 |
|---|---|---|---|
| 水 RHF/STO-3G | 同一 RHF/STO-3G 能量/偶极 | `direct_reuse` | 冷启动和同协议身份相同，能量差为零 |
| 水 RHF/STO-3G 密度 | 水 RHF/6-31G* | `initial_guess_only` | AO 投影后收敛 11 周期，能量为 `-76.00910376515158`，冷启动为 `-76.00910376515175` |
| 水 RHF/6-31G* | 水 B3LYP/6-31G* | `refine_required` | 种子收敛到 B3LYP 目标，能量 `-76.40681537406532`，RHF 与 B3LYP 能量差 `0.3977116089 Eh` |
| 中性水 RHF/STO-3G | H₂⁺ UHF/STO-3G | `reject_and_recompute` | 电子数、几何和多重度改变，目标另行冷启动 |
| 冻结零场密度 | 弛豫外场偶极响应 | `reject_and_recompute` | 冻结导数为零，有限场弛豫导数最大分量 `0.04204105` |
| 未绑定 AO 反转 | 原水偶极 | `reject` | 未知顺序造成偶极差 `2.69792310`，已知带元数据的往返误差为零 |

同一几何下改变基组使能量改变 `1.0460853891 Eh`。这两个数值差异证明方法
和基组是目标身份的一部分，投影初猜没有把结果变成可直接复用资产。H₂⁺
开放壳层目标和拉伸 H₂ 低间隙控制都保留状态与稳定性信息，不能沿用中性闭壳层
响应证书。

## 质量、成本和失败

7 个目标状态全部收敛。完整目标重算共 7 次 SCF，目标状态用时、SCF 周期、
轨道间隙、密度有限性和偶极均封存。身份预检拒绝不消费目标 J/K。状态改变
的目标重算和基组投影精修费用单独记录，不能摊入直接复用收益。当前没有观察到
SCF 失败，失败控制由未知 AO 排列、状态不匹配和冻结响应语义触发，分别返回
拒绝或重算。

已有 GQC 响应实验补充了原生路径证据。水的 GQC 直接、手写、规划和独立 CPHF
逐项一致，冻结响应与独立 CPHF 的最大差为 `4.35757186`。LiH 的有限场门槛
失败仍保留为响应范围反例。Psi4/QCSchema 存档偶极实验只在已绑定生产者轴序、
占据和单位时接受，未知 p 轴和缺占据证据都会拒绝。

## Psi4 独立路径

在锁定的 Psi4 1.10 源码提交 `f2492db10de56b30b188239bdc6b4cfbc4a23bd5` 和
隔离包环境 `python=3.13, psi4==1.10, einsums==1.1.2, libxc-c==7.0.0` 中，
重新计算了水的 RHF/STO-3G、RHF/6-31G*、B3LYP/6-31G* 以及 H₂⁺ UHF/STO-3G。
Psi4 使用 `scf_type=pk`、`puream=true`、同一 Bohr 几何和原点。四个目标与
PySCF 结果的最大能量差为 `5.24×10⁻⁸ Eh`，最大偶极差为 `1.82×10⁻⁸ au`。
`puream=true` 是必要的表示约定，未显式对齐球谐/笛卡尔 AO 时，6-31G* 的
基函数数目和能量会发生可见差异。[Psi4 逐项结果](psi4_result.json) · [运行器](psi4_compare.py)

## 结论

资产可迁移性必须按目标相关科学身份判断。相同协议的状态可直接复用，方法和
基组改变时旧状态最多作为初猜或精修起点，电子数/自旋、AO 顺序、原点和响应
语义不匹配时必须拒绝或重新求解。当前证据只支持固定 RHF/STO-3G 响应协议
的严格边界，不支持跨 DFT、基组、开放壳层或冻结/弛豫导数自动迁移。继续扩大
范围前需要为每个新协议重新取得状态、表示、稳定性和目标误差证据。

## 复现

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .work/response-checks-env/bin/python \
  handoff/gqcdataset_codex_goal/research/experiments/cross_protocol/run.py
python3 handoff/gqcdataset_codex_goal/research/experiments/cross_protocol/verify.py
```

Psi4 和 GQC 的完整源码固定、运行证据和限制见各自的 prior-art 审计。Psi4 新
路径补充了跨后端数值对照，但没有改变迁移分类结论。跨方法、基组、状态和响应
语义仍需按科学身份重新验收。

响应级迁移的独立盲验另见 [#27 response migration](response_migration/README.md)。
同协议序列化响应资产在独立进程中接受，改基组/方法重新求解，开放壳层和低间隙
目标分别拒绝重算或返回 `evidence_unavailable`。
