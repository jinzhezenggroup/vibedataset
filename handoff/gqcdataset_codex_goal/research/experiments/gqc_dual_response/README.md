# DUAL-001　QM9 构型上直接与伴随求解的共同数值基准

本文归档 v1 的原始基准与成本。当前发布参照逐列测量 CPHF 物理残差与读出精度，12 份基态已重算。[v2 科学核验与分子结果](../cphf_v2/README.md)

四份通过零场参考态门槛的分子共请求 36 个 RHF/STO-3G 外场响应标量，28 个通过全部预登记检查。原定 8 个分层中有两个空层、六份实际代表；另外两份代表分别因参考态 SCF 不收敛和外部稳定性检查失败，未获得可用零场态。若以六份代表的全部目标计，覆盖为 28/54。QM9 提供原始几何，新电子态及相应的计算成本见 n5 记录。[原协议](protocol.md) · [所有分层与回执哈希](summary.json) · [外部参考态生产](../qm9_response_assets/index.json)

| QM9 ID | 占虚维数 | 三电场直接 J/K | 三读出伴随 J/K | 直接／伴随最大差 | PySCF CPHF 最大差 | 两步长 FD 最大差，5×10⁻⁴／2×10⁻⁴ | 合格 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000001 | 20 | 41 | 41 | 3.56×10⁻¹⁴ 以内 | 1.17×10⁻⁹ 以内 | 6.73×10⁻⁷／1.04×10⁻⁷ 以内 | 9/9 |
| 000002 | 15 | 30 | 30 | 8.53×10⁻¹⁴ 以内 | 1.12×10⁻¹² 以内 | 1.29×10⁻⁶／2.41×10⁻⁷ 以内 | 9/9 |
| 000003 | 10 | 22 | 22 | 7.11×10⁻¹⁵ 以内 | 2.29×10⁻¹² 以内 | 4.32×10⁻⁷／7.04×10⁻⁸ 以内 | 9/9 |
| 000010 | 77 | 144 | 144 | 9.60×10⁻¹⁴ 以内 | 6.06×10⁻⁶ 以内 | 3.96×10⁻⁵／6.33×10⁻⁶ 以内 | 1/9 |

误差按同一分量在其自身单位中比较。每份原始结果的 targets 包含 3 个笛卡尔电场 × 3 个读出的全部数值、两步长结果、资格和暂缓原因；q0 的单位为 e/原子单位电场，r2 和 zz 的单位为 Bohr²/原子单位电场。000010 只有 z 场下的首原子电荷导数通过，数值为 −0.00234730308305。该分子 x 场下的 z² 读出在 GQC 直接路径得到 5.408018249818305，独立 CPHF 差 6.05953×10⁻⁶，超过 1×10⁻⁸ 门槛。当前证据没有定位这一差异的具体来源。八项未合格观测保留诊断，发布值为 null。[000001](oracles/qm9-000001.json) · [000002](oracles/qm9-000002.json) · [000003](oracles/qm9-000003.json) · [000010](oracles/qm9-000010.json)

## 为什么这两条路径对应同一标签

给定电子读出 O，TensorIR 对 Tr(O dD) 关于占虚旋转作反向微分，生成解算所需的读出右端。每个读出都与其解析表达式和由 GQC 原有轨道 JVP 计算的密度导数点积核对。对固定构型、实受限闭壳层的自伴问题，可以解电场方程 AXᵢ=bᵢ 后读取 cⱼᵀXᵢ，也可以解读出方程 AYⱼ=cⱼ 后读取 bᵢᵀYⱼ。读出组没有把偶极分量作为列，混用直接与伴随时仍可在一个 GQC block 中取得所有被选端点。实际程序生成了 FP64 本地 CPU 共享库，分别执行密度 JVP、Coulomb/exchange、占虚作用、场右端和读出转置。每个分子的核和逻辑程序都有 SHA。相近维数、相同方法名或小迭代残差不单独保证科学兼容。[数值实现](../../../../../scripts/gqc_dual_response.py) · [原始计算事件](events.jsonl.gz)

只存经过真残差检查的 X 或 Y 可服务后续请求。同一旧解在每个实际消费它的轮次重算物理残差；检查范围还绑定几何、AO 约定、参考态、Hamiltonian、扰动及读出的实际算符、原点和 RHS。旧解误用、重算校验和的错误数值、跨参考态、形状错误都触发补算。独立科学资格作用于每个最终标量；某一标量未获资格时其原值仅能作诊断。组合场的实际原始读出也带有该场、原点、右端、各读出与响应问题的身份。000003 的 (1,1,1) 组合场与三个单轴响应的和，对三个读出的最大差为 1.07×10⁻¹⁴ 以内。组合场的一个解是否足以恢复各单轴成员，还取决于事先已知的独立标量及其身份。[缓存、组合场和非有限值控制](cache-controls.json)

## 实际成本和初测边界

首次数值基准包括 4×5 次准备 J/K（每个分子核对物理 Fock 并做两组随机双线性点积）以及 237 次直接和 237 次伴随 J/K。独立复核包含 52 次完整 PySCF SCF，2772 个报告的 SCF 周期、2876 次 SCF J/K，以及 4 个独立 CPHF block，22 次 PySCF J/K 批回调覆盖 58 个密度列。不同软件的 J/K 调用处理的列数可能不同，分别计数。n5 的原始零场生产、失败和存储另有独立回执。表中各自仅有原生三列算子路径的实际工作；它既不是整轮调度对照，也不代表跨用户任务的墙时优势。

初测后为每个输入／读出补存独立算符摘要。每个 oracle 的 operator_attestation 记录新增身份和实际重放成本。用相同输入检查五个 TensorIR 内核，重放所有直接及伴随数值，四份分子均与初测逐分量完全相同。该鉴证另花 20 次准备和 474 次求解 J/K，没有重复 52 次 SCF；首次鉴证写出步骤缺少路径变量，000003 在写出前额外花费 49 次 J/K。最初启动 CLI 遗漏的 sys 导入已修正，计算前就已退出。库内水的符号回归用了 49 次 J/K，000003 初版接口和最终缓存控制分别另用 100 和 118 次。这些验证开销与数据获取策略的执行分开记录，不能用物理算子计数直接宣称端到端提速。原始环境、二进制 SHA、耗时、真实残差和每次 SCF 终态均在小型回执中。

## 复现与接口

在仓库根目录使用现有已锁定源码树，以 CPU 工具链运行。输出目录取新路径。若存在未通过的科学门槛，基准驱动返回 1 并写出全部逐项证据。当前驱动在首个报告中直接记录算符身份，所以新的 summary 哈希会随时间等元数据而改变。

```bash
uv venv --python 3.13 .work/dual_response_env
uv pip install --python .work/dual_response_env/bin/python numpy==2.5.5 pyscf==2.14.0 scipy==1.18.1 h5py==3.16.0 sccache==0.16.0
source .work/dual_response_env/bin/activate
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python scripts/probe_gqc_dual_response.py \
  --index handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets/index.json \
  --out .work/dual_response_reproduction
python scripts/check_gqc_dual_response.py --out .work/dual_response_replay_controls
```

外层规划器只需分子元数据、数组、请求与当前可用资产 ID。可先选择本轮端点，再附上参考表验收已经选好的标量。每次 run_round 原地更新缓存、记录核验和实际求解成本。若调用者只保留标签，仍可用 assess 校验该标签的来源及科学数值，其中源身份的持久化与匹配由标签持有者负责。

```python
from gqc_dual_response import DualResponseModel

model = DualResponseModel(metadata_path, arrays_path, kernel_cache_path)
cache = model.new_cache()
requests = [('x', 'q0'), ('x', 'r2'), ('z', 'zz')]
fields, observables = ['x'], ['zz']
model.attach_oracle(verified_oracle_path)
result = model.run_round(requests, fields, observables, cache)
assert result['counts']['rhs_columns'] == 2
model.save_cache(cache, archive_path)
```
