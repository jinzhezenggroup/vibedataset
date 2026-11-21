# 哪些第三方标量可以进入当前响应补全

在下列实际查到的资产中，有 17 个几何与实验输入逐字节对应，有已发表的水分子偶极–四极响应，也有保存了完整轨道的生产记录。**能直接作为当前九种场响应操作数的第三方历史值为 0。能恢复真实分量请求先后顺序的用户轨迹为 0。** 这项结论限于本次核查的文件、查询和协议。已有 108 个 v2 合格标签来自本项目的计算。用其中一部分模拟仅存标量的生产过程时，十种请求掩码的频率仍是实验设置。[预登记](protocol.md) · [v2 科学协议](../cphf_v2/protocol.md)

| 实物与覆盖 | 实际可用的信息 | 对这轮补全的限制 |
|---|---|---|
| Ramakrishnan 等的 QM9 正式发布，Figshare 1057646 v2，CC0 | 133,885 个 XYZ 成员的表头均有 17 项。共 2,407,753 行原子数据，每行包含元素、三个坐标及 Mulliken 电荷，每个成员另有三个尾行。17 个候选均已用成员 SHA、原子序及坐标与现有两批清单一一配对。例如水 000003 的 O 电荷为 −0.589706 e，电子空间展宽为 19.0002 bohr²，各向同性极化率为 6.31 bohr³。 | 前两项为零场标量；极化率是偶极响应的各向同性量。发布协议为 B3LYP/6‑31G(2df,p)。文件没有各轴电场下的 Mulliken 电荷或电子二阶矩响应、轨道、方向解和逐标签精度证据。压缩包的成员排列不能给出之后消费者请求分量的时间。[原始坐标／标量](https://api.figshare.com/v2/articles/1057646/versions/2) · [作者的字段说明](https://api.figshare.com/v2/articles/1057641/versions/1) |
| MolSSI OpenFF 公共 QCArchive，服务器版本 0.71 | 实际目录 214 项，其中单点数据集 41 项。对已完成记录按 HF/RHF/SCF 和 STO‑3G 查询，冻结返回的前六个 ID 148574276–148574281。六份都是含 Mg、P 等元素的 121 原子体系，保存了静态 Mulliken 电荷，指定 ROHF 和梯度，六个波函数元数据端点均返回 null。用相同筛选加 `driver=properties` 得空列表。 | 单点输出字段、状态、分子电荷、自旋及构型均已核对。六份结果无法提供选定小分子的场导数。专用 driver 查询无法穷尽其他 driver 附带的自定义性质。数据库的创建与修改时间属于计算记录，不能据此生成后续每轴／每读出的请求轨迹。[服务器目录](https://api.qcarchive.molssi.org/api/v1/datasets) · [生产结果 148574281](https://api.qcarchive.molssi.org/api/v1/records/singlepoint/148574281) |
| OpenFF ESP Fragment Conformers v1.0，数据集 347，从完成集合冻结三份记录 | 记录 96510994–96510996 均为 HF/6‑31G* 的能量任务，预先指定了偶极、四极和键级等读出。三份实有波函数元数据。其中 96510996 的 207,087 字节消息已解包，含基组、159 个 alpha 轨道能量及 25,281 个闭壳层轨道系数。 | 该生产者对三个样本选择了保存零场轨道。已解包的载荷没有外场响应解；基组、几何和所求读出也与目标不符。集合元数据列出来源说明，所读元数据中没有数据许可证字段。本仓库保存访问依据、摘要和字段提取。[数据集](https://api.qcarchive.molssi.org/api/v1/datasets/347) · [已解包的记录](https://api.qcarchive.molssi.org/api/v1/records/singlepoint/96510996) |
| QCFractal 既有 13 个 QCSchema 单点／错误 fixture，BSD‑3‑Clause；Psi4 1.10 三个 SCF response 测试，源码附 LGPLv3 | 重新打开全部 13 个压缩结果，11 个成功，3 个输出波函数数组。Psi4 的 `scf-response1/output.ref` 同时给出水分子的 3×3 偶极和 6×6 四极响应表。审读 `cpscf_linear_response` 可见各性质用其本组扰动和本组读出形成方阵。 | 四极测试对应四极–四极收缩，初例的基组为 aug‑cc‑pVDZ。第二例为带重复壳的自定义基组和 B3LYP；第三例包含 UHF/RHF 的偶极极化率。参数、算符和状态均须具体比较。这些是软件测试输入和参考输出。[QCFractal 固定源码](https://github.com/MolSSI/QCFractal/tree/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcarchivetesting/qcarchivetesting/qcschema_v1_data) · [Psi4 响应收缩](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/driver/procrouting/response/scf_response.py) · [水测试原始输出](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/tests/scf-response1/output.ref) |

## 确实有混合响应标量的来源

取得并清点了作者公开的 dm-dp-surfaces 完整 Git 树 `c7e355fd22eb0b66c2135f21601c5ea0709ac6c2`。218 个跟踪文件为一份说明、一份插值源码、216 份 NPY 表。逐个解码了 18×9×11 格点的 FP64 文件，384,912 个值均有限。HF/aug‑cc‑pVTZ 与 PBE0/aug‑cc‑pVTZ 各含 24 个原子中心的秩 1–秩 2 响应表。源码两个入口已审读，实际运行了 `get_dp`。该快照没有记录产生格点的电子结构程序、逐点收敛误差、波函数或分量请求时间；方法来自发布者的目录和说明。快照未附许可证，在此保存文件清单、散列及少量检查读数。[固定源码树](https://github.com/kmherman/dm-dp-surfaces/tree/c7e355fd22eb0b66c2135f21601c5ea0709ac6c2) · [原作者消费程序](https://github.com/kmherman/dm-dp-surfaces/blob/c7e355fd22eb0b66c2135f21601c5ea0709ac6c2/interpolate_dp_dm.py)

在格点 H–O–H=105°、平均 OH=0.96 Å、键长差为零，每次调用实际打开 O、H1、H2 的 63 份表，共 906,192 字节。HF 表的 O_p10_20 原值为 −0.404442887432，作者输出文本写为 −0.40444。即使在格点上，五位小数输出的这项舍入差也达到 2.89×10⁻⁶（表的原生单位）；原数组保留了更多精度。程序消费每个原子中心的球分量并将指定矩阵元对称填充。当前目标需要固定全局原点下的笛卡尔原始二阶矩和首原子 Mulliken 电荷对均匀场的导数。作者的秩 2 表提供五个角分量，未提供电子二阶矩的笛卡尔迹。要从分布式读出转换到全局 zz 还需约定、平移所需低阶量、迹及精度证据；即使建立这样的转换，已发布基组也与目标不同。本次两次调用验证的是程序的固定读入集合，未观测到外部用户的分批访问。[实测消费回执](consumers.json)

## 费用与覆盖

公开 QCArchive 的整批复取用 35 个只读请求，共 9,008,137 个响应载荷字节，与本轮首次冻结的同名文件逐字节一致。三路并发下，各请求耗时之和为 127.61 秒。首次精确 driver 查询在 25 秒时超时，随后重试在 28.58 秒取得空列表。QCArchive 动态目录和按条件排序的记录会变动，已保留查询体、固定 ID、时间和原始响应摘要。公开服务器版本与本地用于理解读接口的 QCFractal 固定源码分别记录。[HTTP 回执](transfers.json) · [服务器端只读查询与波函数接口](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcfractal/qcfractal/components/singlepoint/routes.py)

QM9 官方压缩包为 86,144,227 字节，成员有效载荷合计 230,710,732 字节。本轮三次完整归档检查中，QM9 扫描用时分别为 28.39、48.95、46.60 秒，最后一次涵盖全部 17 份离线复核样本。消费测试另执行一次在读取程序输出时中断的 HF 插值（已打开 63 份表），修正文本行解析后，HF 和 DFT 调用各约 0.022 和 0.021 秒。物理求解、新 J/K 和 SCF 均为零。这些读取、网络与校验成本属于本次寻找遗留输入；它们不进入假设已有合格历史的每轮块求解时间。[全档核验回执](inspection.json) · [数值、成员样本与逐文件覆盖](assets.json.gz)

## 复核

无需网络和科学依赖即可检查留存的 17 份 CC0 原始成员、来源绑定、生产记录投影、完整水格点树的 Git 身份及实际执行的读取证据。在仓库根目录运行以下命令。

```bash
p=handoff/gqcdataset_codex_goal/research/experiments/legacy_response_assets
python3 "$p/verify.py"
```

完整复核另需 QM9 的上述两个官方文件、仓库已锁定的 QCFractal 与 Psi4 源码，以及固定的水表树。下列命令把新源与运行文件放在未跟踪目录。已有匹配来源时可直接复用。

```bash
p=handoff/gqcdataset_codex_goal/research/experiments/legacy_response_assets
mkdir -p .work/legacy15/qm9
curl -fsSL https://ndownloader.figshare.com/files/3195389 -o .work/legacy15/qm9/dsgdb9nsd.xyz.tar.bz2
curl -fsSL https://ndownloader.figshare.com/files/3195392 -o .work/legacy15/qm9/readme.txt
git clone https://github.com/kmherman/dm-dp-surfaces .work/legacy15/water
git -C .work/legacy15/water checkout --detach c7e355fd22eb0b66c2135f21601c5ea0709ac6c2
python3 "$p/fetch_qca.py" --out .work/legacy15/qca
python3 "$p/inspect_assets.py" --qm9 .work/legacy15/qm9 --references _references \
    --water .work/legacy15/water --qca .work/legacy15/qca --out .work/legacy15/replay
```

在 Python 3.10、NumPy 1.26.4、SciPy 1.13.1、msgpack 1.1.2 和 zstd 命令行环境中，运行 `probe_consumers.py --water .work/legacy15/water --wavefunction .work/legacy15/qca/wfn-96510996.msgpack --out .work/legacy15/consumers.json` 可重放作者的插值和轨道载荷解包。设置 `PYTHONDONTWRITEBYTECODE=1` 保持上游树干净。以后若服务器改变内容，固定记录仍可按 ID 读取并与当前散列和字段对照，历史筛选结果应保留原日期和分母。
