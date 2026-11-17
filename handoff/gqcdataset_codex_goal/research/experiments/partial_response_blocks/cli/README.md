# 用户入口的部分历史与回退验证

使用 QM9 000003 的新数据库和早先同协议实际算出的两项或四项标量，普通三轴为 22 次 J/K。默认单块从两项或四项历史出发均只需 20 次。旧的全三轴分开执行对这两种档案分别需要 22 和 36 次。四项/两项旧值各自生产用了 19 次 J/K，每个启动模型的批次另有 5 次准备 J/K。对角与错位的非对角请求均通过原独立门槛。新计划对直接数值的最大差小于 1.25×10⁻¹⁴。

重开数据库重复查询已发布值，模型初始化和 J/K 都为零。对第一次双列真实求解故意仅给一次迭代，求解器在花费 4 次 J/K 后按真实残差拒绝。入口随后用原科学协议补算三轴，另用 22 次 J/K，三项都与原直接结果完全相同，回执共记 26 次。可检查该失败块的列数、失败原因与拒绝前实际费用。[逐客户摘要](verification.json) · [完整已测批次](batches.json.gz)

独立的 14 次历史工作流、9 次事务/并发控件和 11 次跨目录/旧版本控件也已重放。原有目录、科学身份和历史摘要仍可使用。初版专用控件与最终批次的额外开销单列，每次实际发生的建模与求解均计入测试，不与生产对照相加。[回归记录](regressions.json.gz) · [各次执行开销](test-costs.json)

从仓库根目录可运行这一对清单。两个独立数据库模拟原生产者只转交标量的情形。若同一数据库已有完整方向向量，程序会考虑这些向量。

```bash
e=handoff/gqcdataset_codex_goal/research/experiments
python scripts/complete_response_dataset.py --requests "$e/partial_response_blocks/cli/cross-two.jsonl" --cache-db .work/cross-producer.sqlite --out .work/cross-history.json
history_sha=$(sha256sum .work/cross-history.json | cut -d' ' -f1)
python scripts/complete_response_dataset.py --requests "$e/response_dataset_cli/diagonal.jsonl" --history "$history_sha" .work/cross-history.json --cache-db .work/cross-consumer.sqlite --out .work/cross-completed.json
```

在仓库根目录使用[科学环境](../../response_planning/README.md)，执行以下命令生成新回执。

```bash
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python handoff/gqcdataset_codex_goal/research/experiments/partial_response_blocks/cli/check.py --work .work/partial-cli-new
```
