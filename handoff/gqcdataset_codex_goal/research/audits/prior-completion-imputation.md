# 利用已有属性预测缺失属性

Schofield、Jin、Miller 与 Savoie 的论文直接研究分子属性缺失时如何利用同一行已有的属性。作者将 `v1.0.0` 标为论文冻结版本，对应 `386217f233f5607a6c69e09c8bd9375fbde06444`。本次取得完整 43 个跟踪项，包含训练、评估、案例、配置、环境、若干 R² 文本与 MIT 许可证。无子模块和 LFS 指针。论文数据与模型另存于 Zenodo；本次取得一个完整发布权重及表头和 32 行实际数据。Git 树与外部资产分别校验。[期刊论文](https://doi.org/10.1039/D5DD00546A) · [作者冻结版本](https://github.com/Savoie-Research-Group/mol_prop_imputation/releases/tag/v1.0.0) · [作者数据及权重](https://doi.org/10.5281/zenodo.17519032)

## 输入、训练与真实执行

本次跟踪 `random_drop_prop2prop` 中不输入结构的路径。训练脚本先按数值范围筛选，使用训练集拟合 MinMaxScaler 并把特征映射到 0–100 标度，按配置选前 22 个目标。动态数据集复制输入行后逐元素随机屏蔽，用 −100 作为缺失标记，同时保留未损坏的目标；示例配置训练损失为 MSE。评估脚本用另一份显式掩码挑出每一列被隐藏的样本并导出预测/真值。普通统计误差的分母应保留筛选、缺失生成和数据切分规则。[训练实现](https://github.com/Savoie-Research-Group/mol_prop_imputation/blob/386217f233f5607a6c69e09c8bd9375fbde06444/random_drop_prop2prop/Train_attn.py#L85) · [动态屏蔽](https://github.com/Savoie-Research-Group/mol_prop_imputation/blob/386217f233f5607a6c69e09c8bd9375fbde06444/random_drop_prop2prop/Train_attn.py#L218) · [评估子集](https://github.com/Savoie-Research-Group/mol_prop_imputation/blob/386217f233f5607a6c69e09c8bd9375fbde06444/random_drop_prop2prop/Eval_attn.py#L134)

每个属性有独立线性嵌入和可训练的缺失向量。随后 Transformer 编码各输入，按属性分别解码标量。运行该固定代码的 `Model(include_quad=False)`，严格加载作者归档中的 21,054,998 个模型参数。受控输入仅观测一列（归一化值 50）时，隐藏 gap 的输出从全缺时的 24.1977 变为 19.4432，均为模型归一化单位。原样传入一个 NaN 的对照产生 704 个非有限输出；实际应用需要把缺失值按训练契约编码。未运行其他结构模型、本次训练或全论文评分流程。[模型](https://github.com/Savoie-Research-Group/mol_prop_imputation/blob/386217f233f5607a6c69e09c8bd9375fbde06444/random_drop_prop2prop/model_random_drop.py#L18) · [运行记录](../experiments/prior-completion-imputation/result.json)

## 等精度目标的反例

作者归档的合并 CSV 含 SMILES、split、28 列属性数据。首 32 行均标为 train。取其 `homo_lumo_gap` 作为目标，隐藏全部 22 个标量输入，关闭结构和四极矩输入。32 个模型输入相同，32 个 gap 预测也相同。原始 gap 列介于 3.592591666456 与 4.145301263111 之间。对共同物理单位下任一共同预测值，至少一个样本的绝对误差大于等于极差的一半，即 **0.2763547983275 个原列单位**。这个简单下界来自两端点的三角不等式。它检验全缺情形中的信息损失，只约束这一属性输入模式。没有将归一化预测直接和原始标签比较。这 32 行也不能用作泛化性能评估。[数据记录](https://doi.org/10.5281/zenodo.17519032) · [探针](../experiments/prior-completion-imputation/probe.py)

对 GQC，以已收敛、同身份的分量或合法算符恒等式消除求解，可以检验目标数值是否仍满足原协议。这项插补工作的直接输出是预测。在保持目标精度的方案里可将预测作为计算选择或初猜；最终须用目标协议重新验收，计入验收、精修和失败回退。把预测的分数与波函数投影或目标 SCF 的数值误差合并会失去可比性。对于无需保持逐条 QC 数值的预测任务，这套模型提供了利用已有标签的直接基线。

## 复现和外部资产

选用 Zenodo 发布的 `model_random_drop_8_cp_overall.pt`，解出 84,279,982 字节，SHA-256 为 `5c87f90555fca68a0d485b9befaf71e41647a67b0637e85579d28d6540ededfb`。CSV 摘要为 `37d591e2a33dbeea64369b9336d1d8a3f7f33a1b7f1b258fee7686eb5650ebb6`。两者来自 CC-BY-4.0 记录，下载操作仅请求有界的 gzip 压缩流前缀，分别读取 77,916,160 与 10,240 字节以取得完整指定成员或数据行。源端整包的 MD5 已记录，本机未校验两个完整压缩包。另用两个 128 KiB 和一个 32 KiB 的范围读取辨认归档布局与 CSV 列。硬件为本地 x86-64 CPU，前向使用一线程、PyTorch 2.2.0+cpu、Python 3.10.12，三批前向合计实测 0.919 秒以内。本次成本包括下载与推理；作者训练成本未知。[取数回执和外部文件校验](../experiments/prior-completion-imputation/assets.json) · [模型和运行环境](../experiments/prior-completion-imputation/result.json)

在仓库根目录执行，需先取得上面的固定 Git 树。

```bash
probe_dir=handoff/gqcdataset_codex_goal/research/experiments/prior-completion-imputation
uv venv --python 3.10 .work/prior-completion/torch-venv
uv pip install --python .work/prior-completion/torch-venv/bin/python numpy==1.24.3
uv pip install --python .work/prior-completion/torch-venv/bin/python 'torch==2.2.0+cpu' --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
python3 "$probe_dir/fetch_assets.py" .work/prior-completion/published-new
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .work/prior-completion/torch-venv/bin/python "$probe_dir/probe.py" .work/prior-completion/published-new
```
