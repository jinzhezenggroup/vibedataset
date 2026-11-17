# 交接材料下载

[gqcdataset_codex_goal_20261118_rebuilt.zip](gqcdataset_codex_goal_20261118_rebuilt.zip) 是本次仓库文档与工具的快照。解压后的 `vibedataset-handoff/` 保持仓库路径，包括根 AGENTS.md、README、交接材料、issue 映射与文件清单。

这是依据当前可见对话重建的版本，不是此前下载失败 ZIP 的字节副本；不含当前未取得的两份原始 PDF，也不含完整第三方源码。材料来源见 [PROVENANCE.md](../handoff/gqcdataset_codex_goal/PROVENANCE.md)。后续研究进度以仓库 main 和 issues 为准；压缩包保留本次交接快照。

SHA-256 校验文件：[gqcdataset_codex_goal_20261118_rebuilt.zip.sha256](gqcdataset_codex_goal_20261118_rebuilt.zip.sha256)。在下载目录执行：

```bash
sha256sum -c gqcdataset_codex_goal_20261118_rebuilt.zip.sha256
```

快照内 `handoff/gqcdataset_codex_goal/MANIFEST.json` 记录文件清单与散列。清单相对仓库根目录，不包含清单自身或 downloads 目录，以避免校验和循环。它只描述交接快照，不证明第三方源码已获取或科学实验已完成。
