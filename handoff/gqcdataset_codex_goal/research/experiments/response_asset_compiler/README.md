# Response asset compiler（Issue #39）

`scripts/compile_response_assets.py` 把几何、method、basis、charge、multiplicity、AO 表示、原点、单位和精度绑定成 source/target identity。相同身份输出 `direct_reuse`，方法/基组变化输出 `refine_required`，状态身份变化输出 `reject-and-recompute`。计划生成不加载 oracle 或 scorer。

固定计划包含 17 个同协议 direct reuse、2 个 refine-required 和 1 个开放壳层 reject。每行把质量证书标为 `independent_scorer_required` 或 `evidence_unavailable`，不能把残差估计冒充独立证据。`verify_response_asset_compiler.py` 检查身份、分母和 truth-leakage flags。

它是 #38 PreparedPropertyBatch 的身份/资产入口。真正把 density、DF/JK、响应向量编译成 GPU resident 程序，需要 #37 的 profile 和 #40 的 Hessian/CPKS 主负载。

`gpu-assets.json` 将官方 GPU4PySCF C 臂的 51 条 request receipt 编译为 identity-bound GPU response assets，保留 response vectors、AO response densities、target、源 receipt hash 和独立 scorer certificate。`gpu-assets-verification.json` 独立检查 manifest/geometry identity、字段覆盖、asset SHA 和 51/51 scorer accepted，结果为 passed。该步骤复用已封存 C receipt，不重新运行 CPHF，producer 也没有加载 scorer。

这组 51 个 direct assets 只覆盖同一 RHF/STO-3G 协议。跨方法/基组 refine、开放壳层 reject、损坏/过期资产和完整 response certificate frontier 仍由计划文件保留为未完成边界。

`gpu-assets-negative-controls.json` 还保留了三种 verifier 负对照。陈旧 asset hash、错误 geometry identity 和缺失 response density 均得到 `reject-and-recompute`，没有把损坏资产静默接受。
