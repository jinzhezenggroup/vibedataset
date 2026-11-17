# 重跑 Materials Cloud 的分子参考程序

本实验区分零场 Fock 固定时的轨道响应和重新收敛 Kohn–Sham 有效势时的响应。测试对象为发布归档的 QM7 甲烷首帧，以及同一作者关联 Git 分支的水首帧。能量、偶极、轨道占据、几何、AO 顺序、基组参数摘要、XC 标识、零场求解和两个独立响应对照均记入结果。[审计](../../audits/mlelec-archive.md) · [Materials Cloud v1](https://archive.materialscloud.org/records/4vezc-jtt98) · [计算结果](result.json)

## 获取与复现

从仓库根目录运行。发布单位提供的归档约 1.16 GB。命令向新的 `.work/` 子目录写入结果，已有 `_references/mlelec_qm7` 时检查固定提交和工作区。归档流式解压以建立完整成员清单，仅保存本实验用到的八个成员。原始 tar 仅供读取。

```bash
set -euo pipefail
exp="$PWD/handoff/gqcdataset_codex_goal/research/experiments/mlelec_archive"
wrk="$PWD/.work/mlelec-replay"
mkdir -p "$wrk"
if [ ! -d _references/mlelec_qm7/.git ]; then
  python3 handoff/gqcdataset_codex_goal/tools/acquire_sources.py \
    --plan handoff/gqcdataset_codex_goal/research/acquisition_plan.json --ids mlelec_qm7
fi
test "$(git -C _references/mlelec_qm7 rev-parse HEAD)" = 9c34bd9e1351770d3ac5b0887ecf0a98da317417
test -z "$(git -C _references/mlelec_qm7 status --porcelain)"
if [ -f .work/intake2/mlelec-dataset.tar.xz ] && [ -f .work/intake2/suman.json ]; then
  python3 "$exp/inspect_release.py" \
    --record .work/intake2/suman.json --archive .work/intake2/mlelec-dataset.tar.xz --output "$wrk/verified"
else
  python3 "$exp/inspect_release.py" --download --archive "$wrk/dataset.tar.xz" --output "$wrk/verified"
fi
uv venv --python 3.11.17 "$wrk/env"
uv pip install --python "$wrk/env/bin/python" \
  pyscf==2.3.0 ase==3.22.1 numpy==1.24.4 scipy==1.10.1 h5py==3.10.0
env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  "$wrk/env/bin/python" "$exp/probe.py" --verified "$wrk/verified" --output "$wrk/response"
python3 "$exp/verify.py"
```

`inspect_release.py` 将正式 DOI、版本、长度、发布方 MD5 与此处固定的 tar SHA-256 交叉验证，再与完整 Git 树比较源码内容。索引解压后的 SHA-256 应为 `46c8319e89370b22b946afdd5e54cb117a2822230acb5a11204bb70177d4f2fb`。回执中的墙钟时间、操作时间戳与不同工具链生成的 gzip 包头会随运行环境变化。若另需校验 v1 记录列出的两个文本附件，可直接使用以下小流量命令。下载的信息先经官方 MD5、长度和本文独立记录的 SHA-256 验证。[版本、作者、许可、树和内容哈希](release.json) · [官方文本附件摘要](receipts.json)

```bash
python3 - "$exp/receipts.json" <<'PY'
import hashlib
import json
import sys
from urllib.request import urlopen
for attachment in json.load(open(sys.argv[1]))['text_attachments']:
    with urlopen(attachment['url'], timeout=30) as response:
        content = response.read(65537)
    assert len(content) == attachment['bytes']
    assert 'md5:' + hashlib.md5(content).hexdigest() == attachment['publisher_checksum']
    assert hashlib.sha256(content).hexdigest() == attachment['sha256']
    print(attachment['name'], len(content))
PY
```

## 判据和实际成本

`probe.py` 直接调用已核验 SHA 的发布脚本 `single_point`，观察内层 `get_output` 对 `mf.eig` 和 `mf.get_veff` 的调用顺序。其余路径独立求固定 Fock 闭壳层解析结果、含诱导势的 CPKS，以及两个步长的 ±x、±y、±z 自洽有限场。CPKS 每次施加实际 RKS 响应核，每个分子的额外一次核调用计算真残差。有限场各自冷启动，使用源程序的零场网格、泛函、收敛设定及分子对象。结果给出原子单位下 3×3 张量的逐分量差异。此处固定核与有限场计算均取确定性输入，没有随机种子。[实现](probe.py)

预设最大分量容差为固定 Fock 解析式与源程序 10⁻⁵、自洽步长一致性和 CPKS 对两个自洽有限场各 2×10⁻³。为区分物理定义，要求源程序与任一自洽结果的最大绝对分量差均超过 10⁻²。日志用 UTC，预先记录每个操作开始，完成后追加状态、耗时、能量、偶极或响应真残差。水、甲烷全都达到预设判据。核分批调用的实际 RHS 宽度由求解器决定。[数值与阈值](result.json) · [逐操作观测](attempt-2.jsonl.gz)

| 已发生的成本 | 数量或时间 |
|---|---|
| 大归档已完成的下载、此次顺序解索引 | 下载 369.811 秒，流式核验与完整索引 66.278 秒。另复用固定 Git 树和原接收记录。 |
| 成功的单线程 CPU 重算 | 2 个零场 SCF、24 个有场 SCF、2 个三右端 CPKS。两例冷启动零场分别 7、6 轮，有场共 156 轮。CPKS 求解调用响应核分别 7、6 次，每例另用一次核做真残差验证。28 项计算耗时相加 15.876 秒；从几何读取至结果生成约 16.343 秒。 |
| 首次失败与总计 | 首次在相同的 28 项计算结束后，最终 JSON 遇到 NumPy int64 编码错误。保留全部操作日志，改正标量编码并添加逐分子写出后完整重跑，判据未更改。两次合计 4 个零场 SCF、48 个有场 SCF、4 个三右端 CPKS、0 次模型参数更新。两次计算段记录的总时长 31.469 秒。 |

`verify.py` 只依赖 Python 标准库，可离线核对本目录留存的摘要、成员观测、两次操作日志以及两种场步长的有限差分。重新跑完 `probe.py` 时，程序会按同一组判据检查新结果，保存在 `$wrk/response/result.json` 中。归档 HDF5 载荷仅查询数据集路径、类型、形状与前两个原始字节。未读取反序列化后的已发布模型/张量。不同机器的跨次运行应比较科学判据和来源标识。[首次日志](attempt-1.jsonl.gz) · [两次成本](receipts.json) · [离线核验](verify.py)
