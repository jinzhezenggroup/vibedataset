# 按输入清单补全 QM9 响应

在仓库根目录使用 DUAL-001 的环境和固定源码。输入为 JSONL，一个对象请求一个标量。source 填写固定版本的 QM9 坐标文件元数据地址；record_id 接受整数 QM9 ID 或形如 qm9-000003 的名称。field 取 x/y/z，observable 取 q0/r2/zz。程序保留每条请求、单位、构型及文件散列、问题身份、原始诊断和发布值。可附 request_id 或 expected_problem_identity。每条输入均有输出，空行作为分隔符。默认的科学定义、基态与独立验收门槛见关联协议。[科学协议](../gqc_dual_response/protocol.md) · [首轮输入](first.jsonl) · [追加输入](append.jsonl)

```bash
source .work/dual_response_env/bin/activate
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
examples=handoff/gqcdataset_codex_goal/research/experiments/response_dataset_cli
python scripts/complete_response_dataset.py --requests "$examples/first.jsonl" --cache-db .work/my_response.sqlite --out .work/response_first.json
python scripts/complete_response_dataset.py --requests "$examples/hit.jsonl" --cache-db .work/my_response.sqlite --out .work/response_hit.json
python scripts/complete_response_dataset.py --requests "$examples/append.jsonl" --cache-db .work/my_response.sqlite --out .work/response_append.json
```

默认源入口是 experiments/qm9_response_assets/index.json 与 experiments/gqc_dual_response/summary.json，二者支持显式传入。请求文件也可由标准输入提供。输出文件以一次原子替换发布，out 取短横线可写到标准输出。全部请求通过时退出 0；部分参考态未取得、请求错误或科学拒绝时输出完整批报告并退出 1；全局参数／目录不可用时退出 2。数值资格由每个标量独立判断，暂缓发布项的 value 为 null，实测值及原因在 diagnostic。当前源索引包含 6 个预选 QM9 ID，其中 4 份有已通过门槛的零场态；其他 QM9 ID 需先生产并登记参考态。

## 缓存与恢复

SQLite 的每个科学身份绑定版本化来源、原结构 member/SHA、S/h/F/C/ERI 等参考文件散列、参考态、扰动与读出的身份、单位、原点、方法、精度、容差和独立验收版本。相同标量命中时，先核实来源／摘要和独立证据，无需构造 GQC 模型。未命中时由最小端点覆盖选择同一 GQC block 的直接和伴随右端。留存的向量是候选初值之外的响应解，供同一物理方程在后续目标中使用；实际消费时仍重新验证对应的真残差。科学拒绝会保留原始诊断。独立 oracle 只对已经取得的标量作质检。

每个分子在实际核验或求解前提交 started 收据。随后在 SQLite 写事务中重新读取当前命中项，同一事务提交合格标量、向量及 completed 收据。两个并发客户端会串行更新同一数据库；失败时回滚此分子的新状态，并给已发生的操作计费。异常终止可留下 started 状态，表示尚无已提交的终态。若数据库已提交而输出文件发布前进程退出，重试会复用已提交的数值。数据库和输出文件应置于支持 SQLite 文件锁与原子重命名的文件系统。

## 小型实测

使用提交 `eaa6def` 的入口启动 9 个独立 OS 进程。首轮 2 个不同水分子目标共享 1 个 RHS，共有 5 次准备和 18 次科学 J/K；同批重复项直接关联第一条结果。第二进程的纯标量命中没有构造 GQC 模型，准备和求解各为零。随后追加 x→zz 用 1 次物理残差复核，新增 RHS 为零。000010 的 x→zz 实际求解后因为独立 CPHF 门槛未通过而留空。注入的向量写失败发生在标量写入之后，两张科学表均回滚；新的独立进程重试后才产生合格标签。两个并发进程同时索取同一新标量，一份科学计算和一个来源 ID 服务了两次请求。验证结束时数据库完整性检查通过，留有 5 个合格标量、4 份向量存档、8 份完成与 1 份失败作业收据。[验证摘要](verification.json) · [9 份完整批输出](client-results.json.gz)

重做所有 CLI 对照需指定一个新验证目录。程序只在该目录的临时数据库中注入异常；已提交的证据不参与新计算。独立参考原始生成使用 DUAL-001 的 `978f303`；从 `60fe2eb` 的实现提取纯标量验收函数后，对 36 个请求的直接值、伴随值、独立值和三类无效值逐项回放，216 项校验结果和 4 项无 oracle 状态均一致。

```bash
python "$examples/verify.py" --work .work/response_cli_replay
```
