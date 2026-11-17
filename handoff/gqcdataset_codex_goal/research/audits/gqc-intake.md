# GQC 接管后的首条审读记录

日期：2026-11-18。#3 **部分开始**，不表示工作基础审计完成。

当前版本：`2791504cc238fe83d328fc1718080642b288222a`；
n2 声明的运行源码：`2bf3fd98da9c6cfba46ca83345e63e1d934e4780`。
二者分别有完整树清点。运行库实际 SHA256 见 `../environment/n2-20261118.json`。

## 已读范围与具体结论

完整读过当前树的 `python/generativeqc/checkpoint.py`、
`python/generativeqc/_warm_state.py`、`src/scf/warm_state.hpp`。
其他文件仅有下述局部阅读，不计入全文件 read。

1. `CheckpointManifest` schema 1 保存密度、源坐标和科学／数值身份；
   不把 DIIS 历史、CC 振幅或响应向量纳入该 schema。`HfWarmState` 自有存储
   保存的是科学 seed 与源诊断，不能把它解释为任意目标的已验收状态。
2. `load_checkpoint` 比较有序原子和去掉几何散列后的 `ResolvedModel`。
   不同基组／表示分到 `transport_required`，不兼容模型拒绝；
   几何或数值控制改变只在 `allow_warm=True` 时接受；
   相同身份、几何、控制标成 `exact_restart`。
3. 即使该分类是 `exact_restart`，返回的 `target_verification` 仍为
   `pending_execute`。可见 Python 实现导入的是 seed，而非直接返回归档能量。
   这是源码层的分类与数据流观察，**还不是本轮运行证明**。
4. 文件校验包含 schema、尺寸、散列、电子数／源元数据等条件；
   `inspect_checkpoint` 与对目标的物理验收分开。原生恢复状态还会经过另一个验证边界。

固定源码入口：
[checkpoint.py](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/checkpoint.py)、
[_warm_state.py](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/_warm_state.py)、
[warm_state.hpp](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/src/scf/warm_state.hpp)。

## 已定位但未完成的行为链

`checkpoint.load_checkpoint` → `_restore_states` →
`generativeqc_batch_restore_hf_warm_states`（`src/api/c_api_batch.cpp`）→
`BatchWarmStarts::restore_warm_states` → 具体 HF/DFT/correlated plan。

本轮局部阅读了 C ABI 的描述符／维度检查及候选复制（约 746–785 行），
并定位 `hf_method.cpp`、`dft_method.cpp`、`correlated_batch.cpp` 的实现。
尚未追完密度的度量验收、热启动回退、新目标 SCF、状态响应消费者和设备实现。
因此 `behavior_traced=false`；不能把部分调用链写成已闭合。

测试文件 `tests/python/test_checkpoint.py` 的 1–174、470–492 行已阅读：
`test_fresh_process_restart_and_independent_reference`、
`test_changed_geometry_is_explicit_warm_start_and_rechecks_target`、
`test_source_convergence_metadata_cannot_bypass_target_solve` 提供后续验收入口。
这里只确认测试内容存在，未运行，没有通过数、速度或科学误差结论。

## 下一项最小判别验证

在运行源码对应的已编译库上，显式固定方法、基组、电荷、自旋和单位，
检验篡改源能量／收敛诊断的合法密度 seed 是否仍触发新目标求解；
同时比较冷启动与热启动目标结果。若涉及力，先按 n2 约定完成两步长差分和独立参考门槛。
不能拿当前源码测试通过与否替代历史二进制身份核验。

## 对路线的局部影响

“保存电子态＋兼容性分类＋再次求解”必须纳入已有强基线。
目前尚无证据证明本项目能在复用数值时保留全部响应依赖，或已超越上述能力。
五条研究主线继续开放。
