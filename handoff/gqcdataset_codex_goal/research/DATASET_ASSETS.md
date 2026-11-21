# 可以实际使用的数据资产

## 第三方遗留响应资产

QM9 正式发布的 133,885 个几何文件中，17 个选定成员的身份逐一匹配。原始 Mulliken 电荷和二阶矩是零场值，各向同性极化率对应另一种读出，且原方法／基组与此处不同。实际 QCArchive 的 HF/STO-3G 梯度记录和 OpenFF HF/6-31G* 能量记录也缺所需的场导数。后者三份均有轨道元数据，并已解包一份完整载荷。作者的水分布式偶极–四极响应则有真实计算表，但基组、原点、张量分量和精度证据不能匹配。故本次生产成本评价只在明确的受控资产条件和请求概率下成立。未取得兼容历史的结论限于上述实际查验范围。[逐资产来源、原始字段与失败原因](experiments/legacy_response_assets/README.md) · [按存储预算重放](experiments/response_benefit/README.md)

首批场景按现有科学信息选择。QCFractal 的上游测试档案用于识别表示和导出协议，ANI 的原始发布用于检验真实的分层缺失，GQC 参考数据及本项目生成的 checkpoint 用于计数剩余的求解工作。每种来源的统计分母独立。

| 来源与范围 | 实际读取的资产 | 能区分的科学问题 |
|---|---|---|
| QCFractal `4ec1ed623f82536076c069dd65a4eb132969d9ed` 的全部 13 个 v1 单点/错误 fixture，5 个不同的有序输入几何。仓库 BSD-3-Clause | 11 个成功记录，8 个未导出波函数，3 个显式导出。其中 H₂、H₂O₂ 有 alpha 密度/轨道/占据，氟乙烷只导出轨道和本征值；13 条均有输入几何和方法。错误记录有无效基组、水的 SCF 一轮未收敛两种原因。Psi4 和 RDKit/UFF 的标量须分开 | 相同模型名和 `energy` driver 不能保证密度可用。氟乙烷可从最终占据清单与轨道重建；删除清单的对照会拒绝。全 s 壳样本无法暴露 p 壳轴次序问题。[逐记录清单](assets/qcfractal-singlepoints.json) · [生成脚本](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcarchivetesting/qcarchivetesting/data_generator/generate_singlepoint.py) · [许可证](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/LICENSE) |
| ANI-1x/1ccx 发布 v1，Figshare 18112775，数据 CC0。HDF5 有 3,114 个根分组 | 依索引 0、1557、3113，取各组前 min(256,组长) 行。在 C₁₀H₁₀、C₄H₅N₇O、O₄ 的 256、18、83 行中，坐标、ωB97X/6-31G* 能量和力均有限；CCSD(T)*/CBS 分别仅 28、6、0 行有值。坐标为 Å，能量 Hartree，力 Hartree/Å。三组已列出的实际字段中没有 AO 轨道/密度、逐行收敛原因或场响应。组名为元素组成，不是分子唯一标识 | 数据论文记载用主动选择生成总体高层子集；单个 NaN 不能区分未选中、失败或其他处理。作者读取器先对全部请求字段求非 NaN 交集，会把 323 行从此次联合分母剔除。抽样频率只描述这三个前缀。[字段形状、数值掩码、切片散列](assets/ani-v1-slice.json) · [原发布](https://doi.org/10.6084/m9.figshare.10047041.v1) · [方法与单位](https://doi.org/10.1038/s41597-020-0473-z) |
| GQC 分子参考与 CP-001 | GQC 当前树的 LiH / H₂O post-HF 参考包带有 RHF 坐标、壳、S/F/C、占据与 AO ERI，用固定源码的生成器和文件哈希界定。CP-001 的 HF schema-1 checkpoint 另存 H₂ 两个几何的实验依据，实际导入的是源密度 | 用已知参考态检验真实响应依赖和多目标共享，用篡改的诊断或不兼容模型检验拒绝行为。两个版本的运行范围单列。[参考生成器](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/tools/generate_posthf_references.py) · [分子响应协议](experiments/gqc_residual_response/protocol.md) · [CP-001](experiments/checkpoint_probe/README.md) |
| QMugs 及其他候选 | 本轮 ETH 官方 item/bundles 端点返回 HTTP 429，仍未取得可核验的波函数记录或生成代码。QM9 几何/标量、其他 QCArchive 实际生产数据集保留为候选 | 当前三类资产已能检验表示、缺失和响应。扩大到生产数据的发生率、跨生产者协议时，重新取得带身份与许可的数据。[访问缺口](SOURCE_GAPS.md) |

## 数据与证据如何复取

在项目根目录运行 `python3 scripts/inspect_qcschema_assets.py` 即按不可变树枚举全部成功及失败单点记录；使用 `.work/audit-venv/bin/python scripts/inspect_ani_release.py` 对原 HDF5 发起只读区间请求。ANI 的 5,590,846,027 字节总文件与发布者 MD5 记录在回执中，当前完整性核验覆盖实际读出的数组。小型离线分量包和每一列哈希可直接用于复核，未把整个第三方数据集引入仓库。[存档态偶极](experiments/archive_dipole/README.md) · [组合能量](experiments/ani_composite/README.md)
