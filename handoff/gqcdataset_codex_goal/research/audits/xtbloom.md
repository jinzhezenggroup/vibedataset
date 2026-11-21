# xTBloom 的原生批次、热启动和失败范围

固定源码 `16ec6bb04629b568b20e012e9b6409fb0ccff0f8`。在保留完整工作树的基础上补取历史和 tags，原 pin 未移动。该提交通向最近发布标签 v0.2.3，距离 49 个提交。使用 CMake Release 在本地从该树构建了 CPU 原生可执行文件，执行上游 `xtbloom.cpu.public_inference`，单个 CTest 条目通过。构建命令选用 LP64 scipy-openblas32，关闭 CUDA 和 Torch 扩展。下列数值行为限于该 CPU 路径。[历史获取回执](../acquisition/xtbloom-history-20261118.json) · [测试、构建和耗时](../experiments/xtbloom-cpu.json)

| 关注点 | 实现、边界与反例 |
|---|---|
| 持续上下文与原生批处理 | `xtbloom_compute` 取得上下文持有的 `Gfn2CpuExecutionCache`。请求用原子偏移打包变长系统；缓存持有各体系的 topology、workspaces 和 workers，`parallel_for` 调度逐体系 SCC，每次重新处理几何。相同上下文可以复用工作区，并非复用目标能量。[C ABI](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/src/api.cpp#L962) · [调度](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/src/runtime/gfn2_cpu_execution.cpp#L2862) |
| 状态与身份 | `make_system_keys` 逐项绑定有序核、分子电荷、未成对电子、自旋通道、外场存在和值、周期信息、输出 flags、迭代上限、收敛容差、温度与混合策略等。坐标可改变。预分配布局和严格 WARM 使用不同判据，例如改变电场可沿用布局，却会使严格 WARM 的键失配。源态保留成功 SCC 的波函数工作区副本，新几何仍经过 `refresh_geometry` 和 `run_scc`。[键](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/src/runtime/gfn2_cpu_execution.cpp#L668) · [波函数与 SCC](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/src/runtime/gfn2_cpu_execution.cpp#L2049) |
| 数值失败的边界 | 对 SCC 不收敛或本征求解失败，保留逐项状态和成功项，失败项的相应输出为 NaN；整批调用仍可返回 SUCCESS。其他异常可结束请求。进入数值执行前撤销旧批次的就绪标记，结束时仅当所有成员成功才允许下一次严格 WARM。对未执行的身份不匹配请求，原生入口在修改调用者输出前拒绝。[状态发布](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/src/runtime/gfn2_cpu_execution.cpp#L2912) |
| Python 策略 | `BatchCalculator.compute` 禁止 warm 与自动分块同时使用。底层 compute 的 WARM 调用遇到 INVALID_ARGUMENT 会改为 FRESH 重试一次，随后按每项 status/converged 更新整批就绪位。错误码触发该重试；只看最终成功会漏记尝试次数。这条包装策略已读源码，当前运行覆盖的是原生 C ABI。[重试](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/python/xtbloom/interface.py#L1618) · [分块](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/python/xtbloom/interface.py#L2436) |

上游测试入口无条件调用 `test_public_warm_start_transactions` 和 `test_one_member_numerical_failure_isolated`。前者检查无前态拒绝、同几何/变几何、改变 flags/自旋/控制、一次 SCC 限制后的 NaN 与后续 WARM 拒绝。后者同批放入正常 H₂ 和核间距 1.1×10⁻⁶ Bohr 的 H₂，要求前者收敛且能量有限，后者状态为数值失败、能量/力/电荷为 NaN。CTest 日志记录整个可执行文件的退出状态，未逐项计数内部 SCC 调用。[事务测试](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/tests/cpu_public_inference_test.cpp#L1639) · [成员失败测试](https://github.com/jinzhezenggroup/xtbloom/blob/16ec6bb04629b568b20e012e9b6409fb0ccff0f8/tests/cpu_public_inference_test.cpp#L2021)

## 复现

在仓库根目录、干净 pin 上执行。实际使用 GNU 11.4.0、CPython 3.13.16、CMake 4.4.5、Ninja 1.13.2 和 scipy-openblas32 0.3.34.0.0。原生 CPU 构建无需 Python wheel 打包或下载 WebAssembly Eigen。

```bash
git -C _references/xtbloom rev-parse HEAD
if [ "$(git -C _references/xtbloom rev-parse --is-shallow-repository)" = true ]; then
  git -C _references/xtbloom fetch --unshallow --tags origin 16ec6bb04629b568b20e012e9b6409fb0ccff0f8
fi
uv venv --python 3.13 .work/xtbloom-audit-env
uv pip install --python .work/xtbloom-audit-env/bin/python cmake==4.4.5 ninja==1.13.2 scipy-openblas32==0.3.34.0.0
source .work/xtbloom-audit-env/bin/activate
provider=$(python -c 'import pathlib,scipy_openblas32; print(pathlib.Path(scipy_openblas32.get_lib_dir())/"libscipy_openblas.so")')
cmake -S _references/xtbloom -B .work/xtbloom-16ec6bb-cpu -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DXTBLOOM_ENABLE_CUDA=OFF -DXTBLOOM_ENABLE_TORCH_EXT=OFF -DXTBLOOM_BUILD_TESTS=ON \
  -DXTBLOOM_CPU_LINALG_LIBRARY="$provider"
cmake --build .work/xtbloom-16ec6bb-cpu --target xtbloom_cpu_public_inference_test --parallel 4
ctest --test-dir .work/xtbloom-16ec6bb-cpu -R '^xtbloom\.cpu\.public_inference$' --output-on-failure
```

项目可以直接继承原生批处理、按项状态和合法初猜。若实验需要跨批重排后逐记录恢复电子态，需增加显式状态导入/导出、身份与失败事务，比较基线应包括在固定批次上持续运行及按成员拆分的独立上下文。该候选能否覆盖更多困难样本、是否抵消额外 IO，尚待测量。
