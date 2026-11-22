# 两个设备上的匹配单卡四臂

两台机器使用同一个 GPU4PySCF 1.9.2 CUDA 12 wheel、PySCF 2.14.0、CuPy 14.2.0 和 cuBLAS 12.9.2.10。每台机器将 A–D、一个预检和一个独立官方 scorer 放在单次 Slurm 分配中的同一张物理卡上。四个生产进程依次运行且各自新建解释器。A/C 直接导入官方安装，B/D 的文件补丁仅施加于作业私有副本，包含反向 dry-run。每臂 17 个几何，每个几何完全相同的三个请求。

| 设备 | Slurm | 驱动 | A/C 生产墙时几何均值比 | 按分子重采样的 95% 区间 | 独立 GPU / CPU 评分 |
|---|---:|---|---:|---|---|
| RTX 5090 | 2401 | 570.86.16 | 1.305766 | [1.251591, 1.362180] | 204/204，204/204 |
| RTX PRO 6000 Blackwell | 5634 | 595.99.02 | 1.288099 | [1.249721, 1.334138] | 204/204，204/204 |

计时先对同一分子的三个请求墙时求和，再对同卡配对的分子取几何均值。首次请求承担启动和 SCF 成本。独立 GPU scorer 用时分别为 208.12 s 和 352.36 s。CPU scorer 另从候选 AO 密度构建真实未预条件残差。两卡各六个损坏对照全部拒绝。四臂各运行一次，区间反映分子间的抽样变化。解释器外部启动、最终发布及独立评分单列。设备型号、驱动、功率上限、完整原始请求、失败分母与评分时间记录在各设备子目录。

在仓库根目录运行以下命令，可从两组原始结果和独立评分重新得到相同统计。

```bash
base=handoff/gqcdataset_codex_goal/research
python3 scripts/compare_matched_single_gpus.py \
  --root "$base/environment/gpu4pyscf-20261122/single-gpu-pairs" \
  --manifest "$base/experiments/attribution_4arm/manifest.json" --out /tmp/single-gpu-pairs.json
```

`paired.slurm` 是 n2 的实际脚本，提交时指定 `--gres=gpu:pro6000:1` 和对应的 GPU 型号过滤。n5 的原始预检通过 pip 下载记录核验 wheel 散列。实际 n5 提交保存在 `rtx5090/submitted.slurm`。单设备内的结果覆盖指定合同和请求密度。[汇总、阈值与成本](summary.json)
