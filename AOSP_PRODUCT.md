# AOSP 产品与 LineageOS 依赖迁移

2026-09-17。源码实现位于 `/Users/bytedance/Project/android-lineage-qemu`。
它是原 `/Users/bytedance/android-lineage-qemu` 及当时未提交改动的独立工作副本。
原目录和正在运行的 StageB v0908 未修改。

## 当前状态

已实现独立产品与构建入口、组件残留验收和若干 AOSP/VirtIO 适配补丁。
**尚未完成完整 Android 构建、启动或 RiskDetector 复测，LineageOS 验收项仍未关闭。**
新入口使用另行准备的 AOSP 平台源码，不能把旧 Lineage framework 切换一个产品名后直接当作 AOSP。

### 2026-09-20 构建执行

已启用 GitHub 自托管 Linux 构建机：32 核、约 128 GB 内存，
准备开始时约 1 TB 可用空间。独立源码位于 runner 工作目录的
`android/aosp16-r4`，旧 `android/lineage` 只作为对象与内核缓存。

- [源码准备任务 35483465871](https://github.com/afacekinuf12/android-lineage-qemu/actions/runs/35483465871)：
  第 2 次尝试成功完成 Android 16 r4 与 VirtIO 的全量同步，共 1022 个项目。
  上次中断留下的 WebView 空仓库被 repo 误判为非浅克隆，开始下载全部历史。
  新增恢复逻辑仅对无 refs、无 shallow 边界的 AOSP 仓库显式获取目标 tag；
  已有历史保持原状。两项真实本地 Git 回归通过。
  首次恢复遇到上次中断留下的 `shallow.lock`；确认无 Git 写入进程后，
  已将 8 个锁文件归档并记录清单。WebView 和 Clang 目标版本均已成功取回。
  平台依赖预检检查 66,130 个源码文件，通过；resolved manifest 已保存。
- [完整构建任务 35484039288](https://github.com/afacekinuf12/android-lineage-qemu/actions/runs/35484039288)：
  构建修订为 `ad87d88`，包含 recovery 网卡修复；源码预检和 lunch 已通过。
  实际配置暴露 AOSP 未提供设备树的内核页大小默认值，查找目录缺少 `4k`；
  现在独立产品在继承设备前显式设置 ARM64/4 KB，19 项产品回归通过，等待重跑。
  直接读取 runner 环境发现其 PATH 不含 `/sbin`，会导致 `modinfo` 不可用；
  已修复。前序排队任务已取消并替换，源码缓存保留供恢复使用。
  前序任务 `35483478149` 第 1 次尝试因源码未准备完成被前置检查正确拒绝；
  其第 2 次排队尝试已由包含 recovery 修复的新任务替换。
- 内核缓存包含 ARM64/4 KB 的 `6.12.81-4k-g4f6bf47200d9` Image 与模块。
  `stage-aosp-kernel.py` 在构建时检查 Image 头、页大小、源码版本、
  每个模块的 vermagic 和必需模块，保存文件哈希。
  已在 runner 完成 Image 头、4 KB 配置、源码版本及全部 109 个模块的
  vermagic 检查，暂存到独立 AOSP 树；110 个文件的哈希与来源已保存。
  内核在新系统中的启动和模块加载尚未验证。
- 新工作流使用 `bp2a` release configuration、全新产品输出和既有签名库。
  产物通过审计后上传 Actions artifact，并保留构建日志和来源记录。
  本流程不创建 GitHub Release。
- `ad87d88` 的补丁 CI 通过；77 项既有测试、4 项内核暂存测试和
  2 项中断 fetch 恢复测试通过，共 83 项。
  前序 `9e1c423` 的 AOSP 下载步骤曾返回 HTTP 503，未通过；
  后续为上游文件下载补充了有限重试，永久错误和重试耗尽仍失败。

**源码同步已完成；本记录不表示镜像构建或实机复测已通过。**
现有 ADB 测试端仍运行旧镜像。

检测证据确认旧镜像有 24 个相关包/overlay、5 个 `ro.lineage.*` 属性、
另外 3 个带 Lineage 目标名的构建属性，以及 8 个相关 feature。
`vendor/lineage/config/common.mk`、`lineage_sdk_common.mk` 和 `version.mk`
分别引入应用/设置组件、SDK/feature、版本属性。
Lineage `frameworks/base/services/Android.bp` 还直接依赖
`org.lineageos.platform.internal`。

## 本次源码改动

| 改动 | 作用 |
| --- | --- |
| `products/virtio_aosp/virtio_aosp_arm64.mk` | 继承设备的 AOSP 产品，使用 `virtio_aosp_arm64` 目标和 VirtIO 产品信息；构建 ID、增量号、指纹和标签由实际构建生成 |
| `products/virtio_aosp/local_manifest.xml` | 为新 AOSP checkout 提供 VirtIO 设备、HAL、图形和 boot manager 源码清单；不拉入 Lineage 的 framework、Settings、SDK 或应用集 |
| `patches/0023-*.patch` | 可选的 Lineage LowPerformanceSettingsProviderOverlay 只在 Lineage 产品安装；AOSP 保留自身 SettingsProvider |
| `patches/0024-*.patch` | 为 VirtIO 的 `boot_devices=any` 提供 by-name 设备识别，并连接设备所需的 vendor init 库 |
| `patches/0025-*.patch` | 允许 VirtIO 使用的 Mesa Android.mk，范围仅该路径 |
| `patches/0026-*.patch` | 为 recovery 创建 sgdisk/libgptf 变体 |
| `patches/0027-*.patch` | recovery 进入菜单时保持以太网启用，避免关闭已由 init 启动 DHCP 的接口 |
| `patches/apply-aosp.sh` | 独立硬件补丁链，保留传感器和 UI Automator 修复；不接入原来的 Pixel 名称改写和按进程属性替换链 |
| `scripts/prepare-aosp-keys.sh` | 从既有签名库复制完整密钥对，独立设置默认签名路径；缺失时失败，不自动换钥 |
| `build-aosp.sh` | 源码依赖检查、全新输出目录、AOSP 产品构建、验收后导出，保存 resolved manifest 和 SHA-256 |
| `scripts/verify-aosp-product.py` | 检查平台源码依赖、分区属性、APK 包名/manifest/DEX、framework JAR DEX、XML/feature/overlay 和核心系统包 |

`build.sh` 默认仍是原 Lineage 流程以保持旧构建调用兼容。
迁移构建必须显式使用 `BUILD_FLAVOR=aosp`；旧 CI 发布流程没有被改成未经完整验证的新流程。

新产品依靠 AOSP 的 Settings、SettingsProvider、SystemUI、Launcher3 和 Provision
配套工作。移除 Lineage SDK 时没有从现有系统卸载 provider、删除包可见性或改写检测结果。
设备支持源码继续保留上游版权、许可证与来源；来源标注不属于需要删除的运行时组件。

## Linux 构建准备

1. 准备全新的 AOSP `android-16.0.0_r4` 平台源码树。
2. 将 `products/virtio_aosp/local_manifest.xml` 放入其 `.repo/local_manifests/` 后同步设备支持项目。
   这份补充清单使用 `lineage-23.2` 分支，尚未在完整 repo sync 中验证所有组合；
   真正构建时会保存解析后的提交 manifest。发生路径冲突时必须先核对来源，不能直接覆盖平台仓库。
3. 提供匹配设备配置的 VirtIO **6.12 ARM64 预编译内核和模块**，
   位于设备 makefile 解析出的 `device/virt/kernel-virtio/6.12/arm64/<page-size>/`。
   `kernel`、`btusb.ko`、`cfg80211.ko`、`virt_wifi.ko` 等必须配套。
   不能从旧的已运行磁盘随意抽取不匹配的内核。当前脚本拒绝依赖 Lineage 内核构建规则的
   `kernel/virt/virtio/Makefile` 路径；源码内核构建需要另行接入 AOSP。
4. 保留现有签名库，通过 `RELEASE_KEYS_DIR` 指定；准备 Linux Android 所需工具链和 `repo`、
   `qemu-img` 等工具。新入口不会替宿主机执行 apt 安装。
5. 从该 AOSP checkout 选择可用的 release configuration，传入 `AOSP_RELEASE_CONFIG`。

检查和构建：

```bash
BUILD_FLAVOR=aosp AOSP_SOURCE_ROOT=/path/to/aosp \
  bash build.sh --check

BUILD_FLAVOR=aosp BUILD_TARGET=arm64only \
  AOSP_SOURCE_ROOT=/path/to/aosp \
  AOSP_RELEASE_CONFIG=<该源码树的release配置> \
  RELEASE_KEYS_DIR=/path/to/existing-signing-keys \
  bash build.sh
```

`--check` 只检查源码与前提，不产生镜像，也不证明所有 Soong、SELinux、recovery 以太网
适配已完成。检查确认 AOSP 的 `EthernetDevice::PreRecovery()` 原本会关闭网卡，
与设备 `early-boot` 启用接口并启动 DHCP 的流程冲突；0027 修复这一冲突。
recovery 地址展示、实际 DHCP、ADB 和 fastbootd 连接仍需启动验证。
当前脚本仅支持 ARM64。

每次构建使用新的 `out/virtio-aosp.*`，通过后导出到本仓库被 Git 忽略的 `aosp-dist/build.*`。
不会复用旧 `system_ext`、`product` 或旧 VM ZIP。失败的输出保留以便诊断。
AOSP 会按自己的规则生成 `dev-keys` 等标签；私有签名不自动等于官方认证或官方 release。

## 本次验证结果

- 77 项主机回归通过，其中 19 项覆盖本次产品继承、overlay 条件、
  缺失密钥、残留属性、APK/DEX 依赖、损坏输入和缺失核心应用。
- 0023 与已有 sensor feature 补丁在缓存的上游 VirtIO 源码上串联应用通过；
  Make 执行确认 Lineage 分支包含该 overlay，AOSP 分支不包含。
- 0021、0022、0024、0025、0026、0027 在 AOSP `android-16.0.0_r4` 原始文件上应用通过。
  sensor 注册代码编译/执行、UI wrapper 主机验证也通过。
- 用本机 aapt2 读取旧测试 VM 的实际 `org.lineageos.platform-res.apk`，
  确认识别到 `lineageos.platform`；不是只用虚构数据验证包名解析。
- 修改的 shell 语法、manifest XML 解析和 Git diff 空白检查通过。

前述为局部源码和主机验证，没有完整镜像构建结果。

## 验收与限制

源检查会拒绝 Lineage SDK/产品目录，以及平台代码里的 Lineage 运行时依赖。
产物检查使用真实 APK manifest 和 DEX，不把改名后的 APK 文件当作组件已经移除。
读取失败、缺失构建字段、坏 XML、缺少核心 provider 等都会失败。
检查覆盖可见的 staging 内容；APEX payload、ELF 中的所有动态依赖、
系统全量功能及硬件认证没有由这个脚本穷尽验证。

以下工作仍需要完整构建机和新镜像：

- 完成 AOSP/VirtIO 源码组合的 repo sync、Soong/链接、SELinux、recovery 与内核模块验证。
- 核对包签名、镜像及生成包内容；全新测试副本启动并验证 Settings、首次开机、桌面和 SystemUI。
- 检查显示、输入、网络、相机与传感器事件流，确认组件替换未损坏硬件路径。
- 同一 APK 复测 LineageOS 分组、24 个相关包标记、构建属性和功能声明。

**不能把本次主机回归和补丁应用通过，描述为旧 VM 的 LineageOS 告警已经消失。**
