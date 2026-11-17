# CP-001：HF checkpoint 是目标结果还是状态初猜？

预登记：2026-11-18。关联 #3；用于检验已有能力边界，不作为最终课题选择。
基于上一轮已锁定完整源码，沿 checkpoint → C ABI → FleetPlan →
密度物理验收 → CUDA HF 迭代路径阅读后设计。

## 判别问题

“exact_restart” 是否让归档的源能量与收敛诊断直接成为新结果？
竞争解释为：兼容性只准许导入密度 seed，目标算符与 SCF 仍重新验收。
如果校验和正确、物理合法但非驻定的密度和虚假能量被直接接受为结果，
则后一解释被推翻；若仍重新求解，则 checkpoint 不能当成任意固定态物性/响应的免求解接口。

## 固定科学与执行条件

- GQC 源码声明 `2bf3fd98da9c6cfba46ca83345e63e1d934e4780`，原生库
  `67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`。
  同时检查 7 个相关已安装 Python 模块的字节哈希；不将当前上游混入该二进制。
- H₂，气相中性单重态，RHF/STO-3G，球谐表示，FP64、direct、CUDA。
  原子沿 z 轴 ±0.7 Bohr（源）及 ±0.8 Bohr（改变几何目标）。
  坐标 Bohr、能量 Hartree、力 Hartree/Bohr。显式禁用自动 preliminary guess。
- 能量收敛 1e-10、密度收敛 1e-8、最大迭代 150、screening 1e-12。
- Slurm main：1 GPU、4 CPU、16 GiB、10 分钟；最多 20 次 GQC 求解入口，
  2 次 PySCF SCF 和 2 次 PySCF 梯度入口。实际失败和未执行项保留，不能用预算上限代替实际调用数。
- 完整机器配置见根目录 `configs/checkpoint_probe.json`；驱动与输入在提交后传至独立运行目录。

## 先验科学门槛

源和目标几何分别先跑冷启动。
沿归一化键长方向用 1e-3、3e-4 Bohr 做中心能量差分，对比解析投影力。
每个误差须 ≤2e-5 Hartree/Bohr；同协议 CPU PySCF 的能量差 ≤2e-8 Hartree，
最大笛卡尔力差 ≤1e-5 Hartree/Bohr。PySCF SCF 收敛阈值 1e-12。
任一门槛失败即停止后续复用实验，不事后放宽容差。

## 机制与反例检查

1. 冷启动导出 checkpoint，再恢复到新 prepared batch：检查分类与 pending_execute；
   执行后比较冷启动 E/F，并检查实际迭代和 persistent_restart。
2. 把源密度改为 AO 表示 diag(2,0)，源能量改为 -100 Hartree、源残差改为 0、
   源迭代改为 1，重算文件校验和。该 RHF 密度在实际源 overlap 下是合法但非驻定的 seed。
   检查仍得到冷启动结果、不是 -100，且目标求解超过 1 次迭代。
3. 改变目标几何：默认导入必须拒绝；allow_warm=True 只能分类为 warm_start_compatible，
   然后与新目标冷启动比较。
4. 源密度减半（错误电子数），重算校验和：必须在物理验收处拒绝；
   拒绝前后导出文件字节应相同，证明原有有效 seed 未被替换，再验证它仍能求解。
5. 目标基组改变为 def2-SVP：allow_warm=True 也必须拒绝，明确需要基组/AO transport。
   只检查不兼容拒绝，不对新基组开展求解。

复用结果容差：能量差 ≤2e-9 Hartree，最大力差 ≤1e-7 Hartree/Bohr。
期望拒绝使用专门状态记录，不能混同为未记录的软件失败。

## 成本与证据

每个 prepare、solve、load、save、transform 与参考调用均先写入 fsync 的 started 记录，
随后记录耗时、成功/拒绝/失败；原始事件保存在 operations.jsonl。
记录配置、输入、驱动、Python 文件与实际原生库哈希、项目提交、Slurm ID、
原始迭代/Fock 计数（如可得）和运行终态。未提供的计数保持 null。
包含资格检查、失败导入与文件操作成本；本轮不声称性能加速或规模化收益。

边界：仅检查这两份 H₂ 几何与指定 HF 构建。导数差分只检验该能量/力路径，
不资格化极化率、Hessian、IRC、开放壳层、其他基组、方法或整个响应系统。
