# 固定源码与论文归档索引

本轮固定 46 个 Git 根快照，含初始化子模块，共 268,477 个文件。xTBloom 保留完整可达历史和标签，其余 45 棵固定树采用浅克隆。141 条人工观察覆盖 126 个不同的 Git 文件。其中 27 个明确为已通读，94 个有行为追踪，51 个参与实跑，这三个集合可以重叠。所有未审读行也在覆盖表中。34 条主张可按固定路径与证据范围逐项复查。[逐文件覆盖](source_coverage.csv) · [人工观察](intake_review.json) · [主张表](claims.csv)

TQ-001、TQ-PRIOR-001 与 PLAN-005 把实际目标误差估计、原作者 DWR 对照和单／双场实测分别绑定到科学输入及固定实现。作者水表的 216 份 NPY 和消费源码有逐文件身份与外部许可记录，数值审查保存在资产清单中。[误差对照](audits/response-target-evidence.md) · [资产与数值覆盖](experiments/legacy_response_assets/README.md)

CPHF-002 追踪固定 PySCF 的 Krylov 停止、块 QR 与日志路径，并运行三个上游 Krylov 测试。新的分子对照使用独立 AO 积分、实测残差、读出误差估计和双步长有限场。[源码及分子证据](experiments/cphf_v2/README.md)

PLAN-004 将同一上游求解器的早期观察与 n5 作业 2048 的新行为审读分别保留。该作业检验一个水分子的部分标量历史及联合组块开销。[固定源码追踪](audits/partial-response-blocks.md) · [n5 对照](experiments/partial_response_blocks/n5/README.md)

正式发布的 Materials Cloud 归档单列于 Git 快照之后。其成员哈希、论文版本关系和作者程序执行证据按归档字节身份核验。[版本锁](sources.lock.json)

| ID | 角色 | 固定提交 | 递归文件数 | 取得状态 |
|---|---|---|---:|---|
| gqc | current | [2791504cc238](https://github.com/jinzhezenggroup/generativeqc/tree/2791504cc238fe83d328fc1718080642b288222a) | 15,690 | acquired |
| gqc_runtime | runtime_source | [2bf3fd98da9c](https://github.com/jinzhezenggroup/generativeqc/tree/2bf3fd98da9c6cfba46ca83345e63e1d934e4780) | 15,106 | acquired |
| xtbloom | current | [16ec6bb04629](https://github.com/jinzhezenggroup/xtbloom/tree/16ec6bb04629b568b20e012e9b6409fb0ccff0f8) | 1,480 | acquired |
| pyscf | current | [2cdf8dc82e67](https://github.com/pyscf/pyscf/tree/2cdf8dc82e679a6a8fc053ce04493d94ad4fc18a) | 2,357 | acquired |
| pyscf_2_14 | release_source | [c63a953ba603](https://github.com/pyscf/pyscf/tree/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8) | 2,295 | acquired |
| libcint_6_1_3 | default_build_dependency | [c72d30662ba0](https://github.com/sunqm/libcint/tree/c72d30662ba08048940c9000cc352a220c867712) | 133 | acquired |
| pyscfad | current | [190fbb4670de](https://github.com/fishjojo/pyscfad/tree/190fbb4670de4c989333a5eb49b401efd5395a3b) | 516 | acquired |
| psi4 | current | [4a005192ac03](https://github.com/psi4/psi4/tree/4a005192ac03d1777915f4449a22f51b3ba06971) | 9,858 | acquired |
| psi4_1_10 | release_source | [f2492db10de5](https://github.com/psi4/psi4/tree/f2492db10de56b30b188239bdc6b4cfbc4a23bd5) | 9,707 | acquired |
| qcfractal | current | [4ec1ed623f82](https://github.com/MolSSI/QCFractal/tree/4ec1ed623f82536076c069dd65a4eb132969d9ed) | 980 | acquired |
| qcelemental | current | [90fda8fa1004](https://github.com/MolSSI/QCElemental/tree/90fda8fa100444da90b47c316a600130af3f1dc4) | 177 | acquired |
| trexio | current | [663f6af01736](https://github.com/TREX-CoE/trexio/tree/663f6af01736344d843dc93d1fa010b35536655d) | 226 | acquired |
| trexio_tools | current | [b07bf8d94cf4](https://github.com/TREX-CoE/trexio_tools/tree/b07bf8d94cf4de9d93118ca023fff9dda5213450) | 50 | acquired |
| mlelec | current | [73da12b404ff](https://github.com/curiosity54/mlelec/tree/73da12b404ff13008d123767f702ca129716dccd) | 419 | acquired |
| gpu4pyscf | current | [5a717f899cb4](https://github.com/pyscf/gpu4pyscf/tree/5a717f899cb40d64a5799ef1df7e3626c505c3bd) | 1,031 | acquired |
| qcdb | current | [d9e156ef8b31](https://github.com/qcdb/qcdb/tree/d9e156ef8b313ac0633211fc6b841f84a3ddde24) | 950 | acquired |
| xtb | current | [4b8c987066c7](https://github.com/grimme-lab/xtb/tree/4b8c987066c7e9bd0c2b727ce026fb9a581c273a) | 579 | acquired |
| tblite | current | [c6f66b93f7b3](https://github.com/tblite/tblite/tree/c6f66b93f7b3ed5db77698021822eaedb8074ce6) | 712 | acquired |
| dxtb | current | [6961f9ceba9c](https://github.com/grimme-lab/dxtb/tree/6961f9ceba9ce813e78a5be1ed5e383b8eb7824b) | 847 | acquired |
| qcengine | current | [64982fd087b9](https://github.com/MolSSI/QCEngine/tree/64982fd087b9b02a76507e2ad2cb75c6f4b4a7e9) | 178 | acquired |
| aiida | current | [31c1dcf59363](https://github.com/aiidateam/aiida-core/tree/31c1dcf5936359c7eaaebaeb335dabe141dfb40e) | 1,870 | acquired |
| pyscf_forge | current | [7e386107da6a](https://github.com/pyscf/pyscf-forge/tree/7e386107da6a463be73cfe67c3e01e087683b164) | 469 | acquired |
| schnorb | current | [38cb268ea431](https://github.com/atomistic-machine-learning/SchNOrb/tree/38cb268ea431b46e3b2088dda48bcd1983462ff5) | 14 | acquired |
| qhnet | current | [594e8bad8cd0](https://github.com/divelab/AIRS/tree/594e8bad8cd0b24a207c818e09b39ccc0aebcd4d) | 1,641 | acquired |
| nabladft | current | [67ca40280980](https://github.com/AIRI-Institute/nablaDFT/tree/67ca402809806e5dd55095e1f095ec9b2683ac41) | 229 | acquired |
| ani1 | current | [62abf3b7deb0](https://github.com/isayev/ANI1_dataset/tree/62abf3b7deb00a5ee03b3749b32873a5654042cb) | 6 | acquired |
| ani1x_ccx | current | [c6b6d20b9915](https://github.com/aiqm/ANI1x_datasets/tree/c6b6d20b9915a4534204800b634fc1f8ee0a08bc) | 12 | acquired |
| torchani | current | [4f9c239eac70](https://github.com/aiqm/torchani/tree/4f9c239eac706e010d3ca1f7c5b7c91abc9ac4c7) | 2,299 | acquired |
| qemfi | current | [883eca5b12c9](https://github.com/SM4DA/QeMFi/tree/883eca5b12c96ca2248fddcc671fcd032696552a) | 24 | acquired |
| multifidelity_gnn | current | [84ee8a280557](https://github.com/davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics/tree/84ee8a280557d7fbc2ebd1042468e21ce8ea16c6) | 44 | acquired |
| hvmc | current | [389bc8abad78](https://github.com/RateTheory/HVMC/tree/389bc8abad78d574ae971289226a27c620a0c351) | 44 | acquired |
| pvmc | current | [0d3340644047](https://github.com/RateTheory/PVMC/tree/0d3340644047abc727896753f48650f8c5205a89) | 48 | acquired |
| vmc | current | [e8ae5d1d8d30](https://github.com/gregongie/vmc/tree/e8ae5d1d8d306379c6ef11621cb3614078900f1d) | 15 | acquired |
| halide | current | [ac9f247583a6](https://github.com/halide/Halide/tree/ac9f247583a633bd64e4b828d9bdcd4ffd952ce8) | 2,745 | acquired |
| mlir | current | [46b9e6906663](https://github.com/llvm/llvm-project/tree/46b9e6906663004e06c1d5be382b84b378d68846) | 191,342 | acquired |
| equiv_dens_ml | current | [f05a471b700b](https://github.com/MihailBogojeski/equiv_dens_ml/tree/f05a471b700ba519ed6f0f86343e1da8c288e412) | 354 | acquired |
| qcmanybody | release_source | [90273ab21e4f](https://github.com/MolSSI/QCManyBody/tree/90273ab21e4f824b286d55411666394c80cf2472) | 108 | acquired |
| mol_prop_imputation | author_release | [386217f233f5](https://github.com/Savoie-Research-Group/mol_prop_imputation/tree/386217f233f5607a6c69e09c8bd9375fbde06444) | 43 | acquired |
| mlelec_qm7 | archive_linked_branch | [9c34bd9e1351](https://github.com/curiosity54/mlelec/tree/9c34bd9e1351770d3ac5b0887ecf0a98da317417) | 129 | acquired |
| dm_phisnet_history | historical_author_source | [eb365d3e4d0e](https://github.com/zyyr17/dm-nn-so3-analytic/tree/eb365d3e4d0e85ccf89740e5fad26970591c5b16) | 190 | acquired |
| phisnet_casnet_fork | later_adaptation | [398f21555414](https://github.com/marquetand/phisnet_fork/tree/398f215554146069a386809a4bd3bed83eddf87a) | 61 | acquired |
| delfta_v1 | qmugs_authors_downstream_delta_learning | [5635b514067b](https://github.com/josejimenezluna/delfta/tree/5635b514067b229227e27143cd87e0ad5057388e) | 51 | acquired |
| openmdao_3_45_2 | release_source | [64175aa55fb5](https://github.com/OpenMDAO/OpenMDAO/tree/64175aa55fb541355b2fb279a6bcfde01e17a878) | 1,239 | acquired |
| cppad_2026 | release_source | [5d51b2aa6d68](https://github.com/coin-or/CppAD/tree/5d51b2aa6d6874c8d561da298a90b3721550d45d) | 1,473 | acquired |
| pymor_2026_1 | release_source | [36a0035e1806](https://github.com/pymor/pymor/tree/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42) | 518 | acquired |
| dm_dp_surfaces | author_release | [c7e355fd22eb](https://github.com/kmherman/dm-dp-surfaces/tree/c7e355fd22eb0b66c2135f21601c5ea0709ac6c2) | 218 | acquired |

AIRS 的 QHNet 和 QH9 共用同一树。GQC、PySCF、Psi4 的独立发行版与当前开发树各自列出。dm-PhiSNet 第一作者历史树早于论文；CasNet 的 PhiSNet fork 与 DelFTa v1.0.0 各为后续应用。六个起始目录无明确仓库 URL 的条目已逐项核查，其中五个原始软件位置仍待获取。[版本角色与具体缺件](SOURCE_GAPS.md) · [六项原始来源](audits/intake-originals.md)

## 正式归档

| 发布物 | 文件身份 | 成员及人工证据 |
|---|---|---|
| Materials Cloud v1，2025-06-02，DOI `10.24435/materialscloud:mg-8f` | `dataset.tar.xz`，1,156,517,180 字节，官方 MD5 `86a870be93068bd7e2bb5a2524524827`，本机 SHA-256 `df6c0894e0063a9c99ad5f94c5989f982dc7186b5476a092b32a780ad9640dfb` | 915 个普通文件、267 个目录，所有普通文件有独立 SHA-256。3 个成员通读、2 个行为追踪、1 个按归档代码实跑。 |

归档声明 CC BY 4.0，链接论文与 Git 的 `qm7` 分支。已取得该分支的固定树；官方记录给出分支名，未载明论文的精确 Git SHA。归档中识别的 12 个源码/笔记本/环境文件与该 Git 树逐一按字节比较，均没有完全相同的 Git blob。原始 1.16 GB 归档可向出版服务获取，仓库保留发布身份、完整成员清单及重复检查入口。[官方发布](https://archive.materialscloud.org/records/4vezc-jtt98) · [校验回执](experiments/mlelec_archive/release.json) · [成员库存](experiments/mlelec_archive/members.json.gz) · [行为及运行证据](audits/mlelec-archive.md)

## 子模块

- `trexio/docs/org-html-themes` 固定为 `20f84182239a537f4c6b533eb65daa2d342428dd`，递归内容见父库存。
- `trexio/python/examples` 固定为 `ad5c60aa6a7bca802c5918cef2aeb4debfa9f134`，递归内容见父库存。
- `xtb/assets/aur/xtb-git` 固定为 `4c3d1a9078ff0e37a3c5ca1388e23394ce26bd8c`，递归内容见父库存。

## 接管验收依据

| #2 验收范围 | 可核查的结果 |
|---|---|
| 版本、用途、访问阻塞及继续处理方式 | 46 棵 Git 树逐项固定 SHA 与角色，正式归档锁定 DOI、版本、文件哈希；六项旧目录分别标明作者历史版本、衍生项目和原始缺件。[来源缺口](SOURCE_GAPS.md) |
| 取得范围与可重做的完整性检查 | 各 Git 树列文件、模式、对象、子模块及 LFS 状态；外部权重、训练输入、数据服务与程序依赖另有具体缺件。正式归档对 915 份普通文件逐一记录哈希。[版本锁](sources.lock.json) |
| 获取、索引、阅读、追踪与运行独立记账 | Git 文件与归档成员使用各自的字节身份。重复审读观察保留各自时间与证据，未读文件也在完整库存内。[人工记录](intake_review.json) · [逐文件表](source_coverage.csv) |
| 后续审计可定位确定版本，缺口持续跟踪 | 34 条主张的固定 Git 源文件或正式归档成员路径均已解析。作者历史源码的论文对应、五项原始代码位置和外部资产可继续核实。[主张](claims.csv) · [遗留缺件](SOURCE_GAPS.md) |

## 重放中央台账

在仓库根目录运行，已有 `_references/` 的固定快照与子模块应与版本锁相符。新的 checkout 可按获取协议重建。每次真实获取都会产生新时间戳；复核已发布库存时使用随仓库提交的压缩文件。覆盖表每个文件一行，同一 blob 的不同日期和证据保留在人工观察文件内，CSV 多个证据路径以 JSON 数组表示。[接管与重新获取命令](INTAKE.md) · [生成器](../tools/build_source_ledger.py) · [验证器](../tools/verify_source_ledger.py)

```bash
python3 handoff/gqcdataset_codex_goal/tools/build_source_ledger.py
python3 handoff/gqcdataset_codex_goal/tools/verify_source_ledger.py
```

取得正式 tar.xz 后可同时复验官方 MD5、本机 SHA-256、长度，以及解包后的每一项名称、类型、尺寸和普通文件 SHA-256。此处以 `MATERIALSCLOUD_ARCHIVE` 指定下载的本地文件。[核验结果](ledger_validation.json) · [归档复现](experiments/mlelec_archive/README.md)

```bash
python3 handoff/gqcdataset_codex_goal/tools/verify_source_ledger.py \
  --archive mlelec_materialscloud_v1 "$MATERIALSCLOUD_ARCHIVE"
```

独立重放新建一个 Git checkout，仅复用已核验的第三方源码树。工作机的未压缩库存没有进入该 checkout。以下命令重新生成发布锁和覆盖表，逐字节比较审读记录、主张、锁、覆盖表及每份压缩库存，并把比较结果写入当前工作区的核验回执。选项 `--preserve-from` 此次核对上一轮固定提交中的 45 个根审查、129 条文件观察、30 条主张。前一版的保留检查同样可以复查。[前一版回执](https://github.com/jinzhezenggroup/vibedataset/blob/b5359eba67e2215bcc0c050cd5d55500ac5ef265/handoff/gqcdataset_codex_goal/research/ledger_validation.json)

```bash
ledger_replay=$(mktemp -d)
git clone --quiet --local --no-checkout . "$ledger_replay"
git -C "$ledger_replay" checkout --quiet --detach "$(git rev-parse HEAD)"
ln -s "$PWD/_references" "$ledger_replay/_references"
(
  cd "$ledger_replay"
  python3 handoff/gqcdataset_codex_goal/tools/build_source_ledger.py
  python3 handoff/gqcdataset_codex_goal/tools/verify_source_ledger.py
)
python3 handoff/gqcdataset_codex_goal/tools/verify_source_ledger.py \
  --archive mlelec_materialscloud_v1 "$MATERIALSCLOUD_ARCHIVE" --compare-replay "$ledger_replay" \
  --preserve-from b5359eba67e2215bcc0c050cd5d55500ac5ef265
```
