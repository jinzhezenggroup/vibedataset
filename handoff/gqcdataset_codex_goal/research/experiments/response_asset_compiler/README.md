# Response asset compiler（Issue #39）

`scripts/compile_response_assets.py` 把几何、method、basis、charge、multiplicity、AO 表示、原点、单位和精度绑定成 source/target identity。相同身份输出 `direct_reuse`，方法/基组变化输出 `refine_required`，状态身份变化输出 `reject-and-recompute`。计划生成不加载 oracle 或 scorer。

固定计划包含 17 个同协议 direct reuse、2 个 refine-required 和 1 个开放壳层 reject。每行把质量证书标为 `independent_scorer_required` 或 `evidence_unavailable`，不能把残差估计冒充独立证据。`verify_response_asset_compiler.py` 检查身份、分母和 truth-leakage flags。

它是 #38 PreparedPropertyBatch 的身份/资产入口。真正把 density、DF/JK、响应向量编译成 GPU resident 程序，需要 #37 的 profile 和 #40 的 Hessian/CPKS 主负载。
