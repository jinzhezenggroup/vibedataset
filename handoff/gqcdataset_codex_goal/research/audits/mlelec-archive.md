# mlelec 的归档基准与静态极化率定义

Materials Cloud v1 附带的参考程序先收敛零场 Kohn–Sham 态，再固定零场有效哈密顿量，求外场作用下的轨道与偶极。用作者列出的 PySCF 2.3.0 和 ASE 3.22.1 重跑，水和甲烷的最大分量分别与完整自洽静态极化率相差 **1.504074** 和 **1.120365** 原子单位。原程序与同一固定 Fock 模型的解析导数在两例中均相合至 3.4×10⁻⁷ 原子单位。这个区别决定 GQC 可以用已存矩阵补全哪一种标签。[原始结果](../experiments/mlelec_archive/result.json) · [归档](https://archive.materialscloud.org/records/4vezc-jtt98)

## 来源与身份

Divya Suman、Jigyasa Nigam、Sandra Saade、Paolo Pegolo、Hanna Tuerk、Xing Zhang、Garnet Kin-Lic Chan、Michele Ceriotti 于 2025-06-02 发布 v1，关联期刊论文与软件的 `qm7` 分支。登记 DOI 为 `10.24435/materialscloud:mg-8f`，登记许可为 CC BY 4.0。论文归档含四组分子体系和石墨烯，以及分开的 reference、模型预测和已训练模型。本次计算取其中分子的默认参考程序。[Materials Cloud 记录](https://archive.materialscloud.org/records/4vezc-jtt98) · [论文](https://doi.org/10.1021/acs.jctc.5c00522) · [归档许可](https://creativecommons.org/licenses/by/4.0/legalcode)

| 材料 | 已核验的范围 |
|---|---|
| `dataset.tar.xz` | 1,156,517,180 字节。发行方 MD5 为 `86a870be93068bd7e2bb5a2524524827`，本地 SHA-256 为 `df6c0894e0063a9c99ad5f94c5989f982dc7186b5476a092b32a780ad9640dfb`。按归档顺序索引 267 个目录、915 个正规文件，对每个文件流式计算 SHA-256，解压后文件内容共 2,254,974,706 字节。[成员库存](../experiments/mlelec_archive/members.json.gz) · [归档回执](../experiments/mlelec_archive/release.json) |
| 正式记录另外两份附件 | 已按发布方长度和 MD5 核验 5,895 字节的 README 和 360 字节的文件说明，SHA-256 已登记。README 将分子参考生成器定位到 `dataset/scripts/pyscf_ref_calc.py`。归档脚本实测优先于 README 对性质的通称。[附件回执](../experiments/mlelec_archive/receipts.json) · [README 原件](https://archive.materialscloud.org/api/records/4vezc-jtt98/files/README.md/content) |
| Git 源码 | 固定 `qm7` 提交 `9c34bd9e1351770d3ac5b0887ecf0a98da317417`，树 `0b700a99488022a81bff992b6813d5d9af466245`，提交日期 2025-05-21，129 个跟踪文件，签出干净，未发现 Git 子模块或 LFS 指针。检查了全树文件名、README、包元数据和源码版权标注，此版本的授权字段只有 `# license = TODO`。单独 Git 源码许可仍未确定。[固定树](https://github.com/curiosity54/mlelec/tree/9c34bd9e1351770d3ac5b0887ecf0a98da317417) · [包元数据](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/pyproject.toml#L8) |

逐项计算归档内 12 份识别出的程序、环境、基组文本和作图源码的 Git blob 对象标识，并与固定树的全部 blob 比对，匹配数为零。归档 `pyscf_ref_calc.py` 的 SHA-256 为 `279e3be8d4cb240f0c75ce3cd39ac622a01614dfd8b068bbec7f98d956e69649`。两份同名训练脚本也有实质差异。归档版 SHA-256 为 `7bad514f871f561dc76be0f605994220399b8b3577a6a700eb058176520cffd5`，设置 seed 42、1,000 epoch、学习率 10⁻³，三个性质损失权重依次为 10⁴、10³、10²。Git 根脚本 SHA-256 为 `d60d995f2e8d1917f4ec2778212580baad897c63a824865e60e92aeaec24aa22`，对应值为 1234、1,001、10⁻⁴、10⁶、0、10³。归档环境列出 PySCF 2.3.0 和 ASE 3.22.1，训练依赖的 `mlelec@qm7` 与 `pyscfad@ml` 都只给分支名，无法据此确定作者训练时的两个 Git 提交。[逐项比对](../experiments/mlelec_archive/release.json) · [Git 训练入口](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/model_train.py#L37)

## 两条可追踪的计算路径

**归档的参考性质。** `pyscf_ref_calc.py` 第 13–18、68–105 行将坐标按 Å 保留六位小数，建立中性单重态气相分子，使用球形 STO-3G、RKS、`b3lypg`、每原子 (99, 590) 格点规格和 10⁻¹⁰ 能量收敛阈值。第 20–65 行取得零场 Fock、重叠、密度、偶极、能量及收敛标志。对零场和三个 10⁻⁸ a.u. 正向电场，分别求解 (F₀ + E·r)C = SCε，更新占据，再从新轨道求偶极，以单边差分组装每列。零场 SCF 的 `converged` 值随结果一起保存。返回时 `mf.mo_*` 已处于最后一个 +z 扰动，后续消费者须从保存的 F₀、S 与零场信息恢复参考轨道。两例调用记录均见首个场对角化之前三次 `get_veff`，零场及有场四次对角化之间或之后均无 `get_veff`，最终 `mf.make_rdm1()` 与保存的零场密度确实存在差异。[发布脚本所在归档](https://archive.materialscloud.org/records/4vezc-jtt98) · [逐次记录](../experiments/mlelec_archive/attempt-2.jsonl.gz)

**由已知几何学习 Hamiltonian。** 归档 `model_train.py` 读取 QM7 的 1,000 帧，按 70/20/10 切为训练、验证、测试。先以小基组 Fock 块做岭回归，再用 Adam 对轨道能量、偶极和极化率的损失微调。固定分支中，`MoleculeDataset` 的小基组和大基组默认是 STO-3G、def2-TZVP，指定 `lb_target` 后采样器从大基组输出间接标签。模型将预测块还原成 AO 矩阵，训练器将预测送入 `loss_fn_combined`，按参考数据的方差归一，以每分子误差范数平方除以原子数平方，再按给定权重反传。例程的测试段将预测与大基组标签比较，并只在求测试轨道能量误差时截取占据能级。这里的跨基组精度来自监督学习，测试样本误差属于经验指标。[数据路径](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/data/dataset.py#L102) · [模型重构](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/models/linear.py#L268) · [损失](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/metrics.py#L84) · [训练器](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/train.py#L90)

固定分支的 `instantiate_mf` 用每帧分子构造 PySCFAD SCF 对象。`compute_batch_polarisability` 将 p 轨道从实球谐顺序转回 PySCF 顺序。正交表象下，`compute_polarisability_from_mf` 用 S 的正平方根将预测矩阵变回 AO Fock，随后求 (F预测 + E·r, S) 广义本征问题、占据、密度和偶极，用 Torch 的 Jacobian 在 E = 0 求导并保留可训练计算图。此处没有对含场自洽固定点求导。完整训练、论文指标、周期体系及大基组归档逐项数值均未复现。上述训练行为来自源码追踪，本次实际执行的是正式归档的分子参考生成器。[性质读出](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/utils/property_utils.py#L212) · [AO 变换](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/utils/twocenter_utils.py#L24) · [默认分子基组](https://github.com/curiosity54/mlelec/blob/9c34bd9e1351770d3ac5b0887ecf0a98da317417/src/mlelec/data/pyscf_calculator.py#L57)

## 可否当作完整自洽响应

选取归档 QM7 的首帧甲烷和 Git 示例水的首帧。水只提供原子序与坐标，按生成器建气相分子，XYZ 中已有的属性和 PBC 标志未进入计算。两种几何均交给未改动的作者程序完成零场 SCF 与性质读出。取其 F₀ 和 S 构造固定有效势下的闭壳层解析导数。对照一使用 PySCF 的三右端 CPKS 与同一零场网格，在残差中再次计算诱导的 J、K 和 XC 势。对照二在 x、y、z 的 ±0.0005 和 ±0.0002 a.u. 独立从默认猜测收敛 RKS，从偶极取中心差分。所有数值均使用原始笛卡尔分量，单位为极化率原子单位。[运行方法](../experiments/mlelec_archive/README.md) · [程序](../experiments/mlelec_archive/probe.py)

| 几何、现场总能量 / Eₕ | 归档程序与固定 Fock 解析式，最大绝对差 | CPKS 与两个自洽差分，较大最大绝对差 | 归档程序与两个自洽差分，较小最大绝对差 | 一个可定位的分量 |
|---|---:|---:|---:|---|
| 水，−75.258025696427 | 2.569×10⁻⁷ | 4.893×10⁻⁷ | **1.504074** | αyy，原程序 5.225505，自洽 CPKS 3.721432 |
| QM7 甲烷，−40.038855302725 | 3.390×10⁻⁷ | 1.924×10⁻⁷ | **1.120365** | αzz，原程序 6.708688，自洽 CPKS 5.588322 |

在闭壳层、正占虚能隙、固定 AO 基、同一有限体系及静态电偶极约定下，固定 Fock 解析式为 `αuv = 4 Σai (rᵘai rᵛai)/(εa − εi)`。两例支持从真实 F₀、S、占据和偶极积分再现这种模型的极化率，文件名 `pol` 单独不足以确定科学定义。若 GQC 目标包含自洽电子松弛，残余程序应保留诱导势响应，用完整 CPKS 或独立自洽有限场验证。若输入矩阵本身来自学习，还需把矩阵预测误差单列。此实验给出区分标签的反例，不能据此估计生产加速比或对整库的误差上界。[完整张量、能隙与真残差](../experiments/mlelec_archive/result.json) · [GQC 响应的既有基线](prior-completion-response.md)

归档的四类 QM7/STO-3G HDF5 容器只检查了结构和载荷的前两个原始字节。偶极和极化率的 `/data`、Fock 和重叠的首个 `/data/data0` 都是 uint8 数组，前缀为 Python pickle 协议 4 标记 `80 04`。没有反序列化第三方对象或将存档中的张量单元与本轮结果配对。表中“归档程序”指使用原发布程序和有身份的几何现场生成的数值。[容器记录](../experiments/mlelec_archive/result.json)
