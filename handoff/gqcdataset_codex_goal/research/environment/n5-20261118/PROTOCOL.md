# n5 的跨节点 HF 密度恢复验证

准备日期为 2026-11-18（Asia/Shanghai）。已知输入为 n2 作业 5382 的 source.vqcp、该作业的文件清单与源码提交。部署固定 n2 的 GQC Python 与库字节，使用 n5 独立 venv 和该机分配的 RTX 5090。两台节点均支持 sm_120。焦点是既有密度能否在第二台节点上被正确验收和继续求解。

- 在 n5 单一 1 GPU、4 CPU、16 GiB、10 分钟 Slurm 分配中，先执行原提交 CP-001 的完整配置。H₂ 核间距 1.4 与 1.6 Bohr，中性单重态，球谐 RHF/STO-3G、FP64、direct。使用相同的冷启动、CPU PySCF 能量/力、两步长力验证和合法/错误导入门槛。先验预算为最多 20 次 GQC 求解，以及 PySCF SCF 和梯度各 2 次。
- CP-001 通过后，在独立的 Python 进程加载同一实际 CDLL，核对归档字节、协议、作业与两侧原生库身份。用原子顺序、电荷、自旋、坐标、基组、方法及控制完全相同的 prepared batch 接受 n2 的密度。
- 导入应为 exact_restart 与 pending_execute。至多再调用 1 次 GQC 求解，要求目标迭代数大于零、收敛、CUDA、persistent_restart、无冷启动回退、执行后状态为 executed。保留迭代/Fock 构建数。
- 与 n2、n5 的冷启动分别比较，能量绝对差不超过 2×10⁻⁹ Hartree，最大力分量差不超过 10⁻⁷ Hartree/Bohr。与同一 n5 分配中独立 CPU PySCF 冷启动比较，分别不超过 2×10⁻⁸ Hartree、10⁻⁵ Hartree/Bohr。
- 保留程序和调度终态、全部尝试、转移字节、耗时、环境与身份哈希。此处检验跨节点状态可移植性，没有给任意新体系、其他导数、加速比或绝对计算精度设定验收。
