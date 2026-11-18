# 不预先求完整目标表的响应质量验收

在 QM9 留出集中，8 份有态分子的 24 个新请求经过数值证据验收，与独立 AO CPHF 参照的最大绝对差为 9.73×10⁻¹²。另 3 份缺态分子的 9 个请求均得到 evidence_unavailable。若历史标量没有可核验的数值误差来源，只能接受 8 个独立新求的 z 目标。用实际量化误差较大的历史时，16 项先进入 refine，普通物理求解后通过。所有项均保留在评分分母中。[逐目标留出评分](holdout/score.json) · [首批评分及错误输入](seed/score.json)

有密集 ERI 的这些小体系，组装响应矩阵并付过稳定性分析费用后，直接稠密求解最便宜。组合路径以 868 次 J/K 完成留出任务，普通原生块为 1,064 次，稠密基线仅需 64 次并取得相同资格。目标相关估计给出了在缺少预先计算的完整真值时按读出接受、精修或暂缓的证据。此次实验支持保留该验收路径，停止用这一受控队列主张原生组合求解带来生产净收益。[预登记](protocol.md) · [留出前冻结](freeze.md) · [逐阶段成本](holdout/costs.csv)

## 科学定义和入口

生产器处理已核验零场闭壳层 RHF/STO-3G 源态，实数占虚响应，原点为坐标原点，核固定。调用方给出来源索引及可信 SHA、请求的场与读出、已有资产的生产清单及可信 SHA。问题、源文件、端点、读出单位、向量和原始测量各有身份。初始历史仅从 GQC 实算 y→q0 和 x→r2，观察者尚未请求 x→q0、y→r2、z→zz。留标量、可留方向、量化标量是同一历史生产的不同保留条件。此处的历史来自受控扩展，不代表外部自然遗留库的分布。

对存档方程 A x=b 与读出 q=cᵀx，误差传递关系为 q−cᵀx̂=cᵀA⁻¹(b−Ax̂)。现有 GQC 程序的符号为 A=−dFov/dX，存档轨道的占占与虚虚 Fock 块完整保留。两个 AO→MO 四指标变换组装 Coulomb/exchange 贡献，一次 SVD 给出 FP64 σ_min。每个实际消费方向独立施一次原生 A，同时计算稠密矩阵作用。候选误差估计由两条残差范数的较大者、残差舍入余量、读出范数、向下调整的数值 σ_min 和点乘舍入余量构成。若维数大于 256、矩阵不对称超限、有效 σ_min 小于等于 10⁻¹⁰σ_max 或作用不一致，规则不给该方向资格。目标容差为自身物理单位中的绝对误差 10⁻⁸。[数值实现](../../../../../scripts/target_response_quality.py) · [独立 CPHF 定义](../cphf_v2/protocol.md)

在固定有限方程上，本方法使用数值奇异值估计，没有对所有浮点张量变换或连续物理模型作严格误差证明。首批水分子 y→r2 的稠密结果与独立 CPHF 差 2.31×10⁻¹²，超过本次离散估计 1.36×10⁻¹² 加独立参照余量 2.06×10⁻¹³。该例仍满足预注册 10⁻⁸ 门槛。留出每个接受项另有同存档矩阵稠密解差以内的实测对照，其中组合路线最大差 3.44×10⁻¹²。本实验没有训练或校准置信区间。[首批完整差值](seed/score.json) · [留出完整差值](holdout/score.json)

组合读出的操作数由各自生产方向给出的区间支持。系数乘上每项误差，再除以目标系数的绝对值，并按项的绝对量加上求和与除法舍入预算。记录各项绝对值之和与最终绝对值之比，结果为零时比值留空。某项超出自身目标容差的实际有限区间仍可参与缩放；最终读出的合成预算必须单独通过。实测历史若缺少证据或改变 RHS、读出、单位、问题或摘要，执行器仅拒绝依赖这些资产的请求。一个合法 JSON 超大整数也只影响对应分量。另有 diag(1,10⁻¹²) 的控制问题，零方向的残差仅 10⁻¹²，而读出误差为 1；稳定性保护返回 evidence_unavailable。大项相消和带符号系数的控制也均有原始数据。[历史故障及独立请求](seed/score.json) · [数值控制](numerical-controls.json)

## 成本与停止条件

以下列出所有 11 个留出分子。准备列含 8 份有态各 5 次原生 J/K。稠密组装、SVD 和线性代数单独计数。求解列包含实际精修，验收列只计额外原生复核。求解器已经实算的终态残差可在预算用尽时供同次、同列精修使用，仍要用稠密乘积复核。每个分子额外物理验收最多 3 次 J/K，并逐分子和实际普通块费用对照。

| 留出任务 | 准备 J/K | 新求解 / 精修 J/K | 验收 J/K | 物理 J/K 合计 | 新原生 RHS | 进程秒 |
|---|---:|---:|---:|---:|---:|---:|
| 历史生产，只读两交叉标量并可保留方向 | 40 | 812 | 16 | 868 | 16 | 19.10 |
| 普通三个场 | 40 | 1,000 | 24 | 1,064 | 24 | 3.34 |
| 已知两标量，x+y 与 z 同块 | 40 | 812 | 16 | 868 | 16 | 3.03 |
| 已存 x/y 方向，仅新求 z | 40 | 500 | 24 | 564 | 8 | 2.59 |
| 已知两量化标量，再普通精修 | 40 | 812+812 | 16+8 | 1,688 | 32 | 4.19 |
| 两标量缺误差来源，仅 z 可发布 | 40 | 812 | 16 | 868 | 16 | 3.03 |
| 已组装的 A 只解请求列 | 40 | 0 | 24 | 64 | 0（另 24 稠密 RHS） | 1.96 |

每行均实际重建自己的数值质量模型，包括 16 次 AO→MO 变换及 8 次 SVD。8 个矩阵累计 512,240 字节，两个变换结果累计 1,024,480 字节，这些是数组载荷。对历史生产的四类归档分别写入 32,188 字节完整标量、39,905 字节完整方向、30,455 字节量化标量和 12,157 字节无误差区间的控制标量。各策略仅读取自己可得的资产。量化的精修控制按 10⁻⁶ 网格储存中点，误差包含实际中点与原值的绝对差。表中历史生产在冷核目录启动，后续任务共用已编译核，各自重新建立并检查模型。物理 JK、稠密代价、文件逻辑大小和单线程进程墙时需同时解释；表中秒数是一次观测。源态生产沿用已发布 n5 记录，本轮没有重新收敛分子 SCF。实际磁盘缓存流量与内核准备中单属编译器的时间未测量。[留出逐阶段字节和时间](holdout/costs.csv) · [源态费用](../qm9_extension/n5-job.json)

同信息条件下允许普通和稠密路线直接解请求，也允许保留或提前计算更多物理资产。历史属于现成的遗留输入时只收新增费用；若在本系统中生产历史再丢弃方向，两标量路线还须另加 868 次 J/K。该质量规则与 pyMOR 的残差、读出范数及稳定性因子有直接前例。量化学特有的工作在于检验具体存档态、算子身份、含误差的旧观测及其消减。在此稠密小体系范围内没有观测到相对最强稠密基线的净收益，不推广至其他资产或更大体系。[冻结时的源码依据和失效条件](protocol.md)

## 复现

生产过程把六个固定程序和核源码放入新的工作目录，分子输入目录仅含来源索引、存档元数据/数组及稀疏请求。Python 文件审计记录实际打开的源文件，拒绝对存放评估数据的实验树的访问。普通与稠密参照运行在候选决策封存后。独立评分器是另一个进程，核对所有资产、原始字节、操作数误差、总分母、物理验证预算和 v2 目录 SHA。这是程序级盲验，队列及既有研究结果已公开。生产与评分的文件和进程边界见各批 seal。[首批封存](seed/seal.json) · [留出封存](holdout/seal.json)

已有来源的正常调用仅需 CLI，`--requests` 可给这套协议下的任意合法请求表。普通或稠密策略可直接从源态运行。下例中的摘要用于展示本地已有资产，跨组织传递须使用可信生产者提供的摘要。

```bash
q=handoff/gqcdataset_codex_goal/research/experiments/target_quality
src=handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets/index.json
src_sha=$(sha256sum "$src" | cut -d' ' -f1)
python scripts/target_quality_batch.py --source-index "$src" --source-sha256 "$src_sha" \
  --mode history --kernel-cache .work/quality-kernels --out .work/quality-history
old=.work/quality-history/report.json
old_sha=$(sha256sum "$old" | cut -d' ' -f1)
python scripts/target_quality_batch.py --source-index "$src" --source-sha256 "$src_sha" \
  --mode mixed --requests "$q/requests.json" --history "$old_sha" "$old" \
  --kernel-cache .work/quality-kernels --out .work/quality-completed
```

在固定的科学 CPU 环境运行盲生产（`--split seed` 或 `--split holdout`），输出必须是新目录。单个水分子可以用 `--split seed --smoke`。普通 Python 即可重新评价已提交的封存结果。

```bash
python scripts/run_blind_target_quality.py --split holdout --out .work/quality-holdout
python3 scripts/score_target_quality.py --sealed .work/quality-holdout/sealed \
  --out .work/quality-holdout/score.json --costs .work/quality-holdout/costs.csv --check-controls
python3 scripts/score_target_quality.py --sealed "$q/holdout" --out .work/quality-score.json \
  --costs .work/quality-costs.csv --check-controls
cmp "$q/holdout/score.json" .work/quality-score.json
cmp "$q/holdout/costs.csv" .work/quality-costs.csv
python scripts/check_target_quality_controls.py --out .work/target-quality-controls.json
```

冻结版本 c6b183c6512f23106d96e6854bf8b9c12fac17f1 的两批均在相同单线程 CPU 配置、同一把性能任务锁下运行。开发探索、正式首批、正式留出和额外的独立 smoke 分别实际花费 1,794、1,838、5,984 和 353 次 GQC J/K，共 9,969 次。原生核、数据、估计函数、版本和每个阶段可从回执和提交定位。温控、系统缓存和跨运行耗时变化仍然存在。[开发探索](development-pilot.tar.gz) · [正式首批成本](seed/costs.csv) · [正式留出成本](holdout/costs.csv) · [独立 smoke](smoke.tar.gz)
