# Issue #27 protocol

生产阶段只生成一个 RHF/STO-3G 水响应资产，封存协议身份、响应向量、读出、
残差和来源散列。它不读取 `cphf_v2`、目标响应表或任何独立评分结果。

评分阶段在新进程中读取封存资产，重新构造目标协议并运行 PySCF CPHF。direct
reuse 只有在响应维度、身份、向量、目标读出和残差同时通过时接受。改基组和
方法的目标响应仍然重算并记录响应证据是否达到当前门槛。UHF 开放壳层和低间隙
控制保留 `reject_and_recompute` 或 `evidence_unavailable`，不更换目标定义来
提高覆盖率。
