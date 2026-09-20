# Risk Detector 1.4 实测与修复记录

检测执行：2026-09-14 至 2026-09-16。对象为 **StageB v0908 的独立副本**。
本次使用用户提供的原 APK，没有修改检测器代码、签名或返回结果。

## 结论

Risk Detector 的六个主分组已展开取证。采集页面去重后有 **42 条具体项目被该 App
标记为“威胁”**，另有 4 个分组标题标记；这不等于 42 个已确认漏洞。
其中大部分来自 LineageOS 来源、调试设置、没有 SIM 和解锁状态。

独立验证确认了两个已有源码修复对应的问题：构建 fingerprint 的 ID/增量号不一致，
以及六类传感器被 HAL 注册但缺少对应 feature 声明。旧镜像尚未包含这些修复。
`CTS Check 1`、`Framework Patch` 未给出具体断言，不能据此确认漏洞或宣布已修复。

## 原包和测试条件

| 项目 | 结果 |
|---|---|
| APK | `RiskDetector 1.4-release-sign.apk`，9,405,091 bytes |
| 包名 / 版本 | `io.liankong.riskdetector` / 1.4，versionCode 10400 |
| SHA-256 | `2c2529a465d87468406114c66618154151c74c90ad1c5e0bb8087abc3cc327b8` |
| 签名 | APK v2 校验通过；仅证明所测文件签名自洽 |
| 证书 SHA-256 | `851413b3754746bcdbc9ce911f5de16271df49869ef534bae60b5439b0b99ed7` |
| ABI / SDK | ARM64、ARM32；min 26、target 35；实际运行 ARM64 |
| 来宾 | Android 16/API 36，`23.2-20260908-jqssun-virtio_arm64only` |
| 原 VM | `7582CCA3-85D0-4013-AAB9-8F2C8DFBC6B0`，测试期间未启动 |
| 测试 VM | `105D2035-B3D3-4338-BF4E-74DD25B707AA` |
| 测试 ADB | `127.0.0.1:15555` |
| 网络 | 实际 QEMU 命令为 `user,restrict=on`，只开放本机 ADB 转发；外网 TCP 和 DNS 探测失败 |
| 权限 | 未授予 READ_PHONE_STATE、读写存储或 Root；INTERNET、QUERY_ALL_PACKAGES 是安装时权限 |

APK 使用 `com.stub.StubApp` 和 `libjiagu.so` 加固。静态字符串出现加固服务地址，
不能据此证明发生上传，也不能证明不存在其他联网行为。因此在限制出站网络的副本运行，
未登录账号、上传报告、安装第三方依赖或启用共享目录。在线服务结果不在本次范围内。

副本从已停止的原 VM 创建，UTM 导入后使用自己的磁盘副本。克隆改变了 VM UUID/MAC，
并继承已有来宾数据；它不是恢复出厂设置后的新设备。来宾墙上时间与主机日期不一致，
UI 中的日期不能当作此次宿主机执行时间。

## 分组结果与判断

| 分组 | App 标记 | 具体结果与判断 |
|---|---|---|
| 基础环境 | 威胁 | 自定义 ROM、LineageOS、解锁检测 Prop/TEE、Framework Patch 共 5 项。前几项符合研究镜像背景；TEE 标签没有提供证书链，Framework Patch 没有具体触发证据。 |
| 风险 App | 未检出 | 展开的包名列表未命中。仅说明其当前规则和可见范围下未命中，不是无风险认证。 |
| 风控信息 | 威胁 | 4 种 ADB 读取、开发者模式、无锁屏密码、2 种插卡检测共 8 项。ADB/开发者模式由 shell 读数确认为 1；SIM 检查还受未授电话权限及无基带影响。 |
| CTS 合规 | 威胁 | `CTS Check 1` 标红；2–5、Version Spoof、Permission Loophole、Sandbox Piercing 等未检出。该 App 的标签不是官方 CTS 测试套件结果。 |
| 风险项 | 威胁 | 24 个 LineageOS 包/overlay，以及 `/proc`、`/proc/cpuinfo`、`/proc/meminfo`、`/proc/sys/kernel/random/boot_id` 4 个路径。包名是项目真实来源；路径标记需核实。 |
| 设备指纹信息 | 未检出 | 仍显示旧 fingerprint、QEMU 输入设备、虚拟网络信息。这个“未检出”不能用来证明符合 Pixel 真机。 |

基础环境的 Root、模拟器、LXC/云手机、Magisk/KSU/APatch、Xposed、Frida、
maps/符号表注入等显示未检出。已知测试目标就是 QEMU VM，所以“模拟器未检出”
尤其不能被解释成真实设备证明。

顶部单独的触摸测试、指纹 ID 测试未作为验收项目运行；没有正式执行完整 CTS、
DRM、服务器证明或电话标识测试。

## `/proc` 交叉验证

在 shell 和检测 App 的 `/proc/<pid>/mountinfo` 均观察到一个正常 procfs 挂载：

```text
/proc  filesystem=proc  root=/  options=rw,relatime
superblock options: rw,gid=3009,hidepid=invisible
```

没有以上三个文件路径的独立覆盖挂载，也没有在该检测进程看到 property spoof
目录的绑定挂载。`statfs` 对四个路径均返回 `proc` / magic `0x9fa0`。
SELinux 为 `Enforcing`。LineageOS `lineage-23.2` 的
`system/core/init/first_stage_init.cpp` 本身以 flags=0 挂载 proc，
其配置与这里的挂载选项一致。

这支持“本次未观察到这些文件的独立覆盖挂载”，不支持“挂载绝对可信”或
“检测器一定误报”。闭源规则可能检查了其他属性；没有为了去掉标签而改写
mountinfo、文件内容、inode、SELinux 策略或内核返回值。

## 已落实的修复

### 1. 修复项目审计脚本的错误通过语义

原 `tools/audit-fingerprint.sh` 会把空属性、失败的文件读取、未匹配到
goldfish/x86 关键词判为 PASS；仅检查 `ro.hardware.egl=angle` 也不能发现
实际 SwiftShader 路径。现在由 `tools/runtime_audit.py` 实现：

- 必须明确指定 ADB serial；每条命令与整体执行都有超时。
- 读取失败或缺少依据为 `inconclusive/error`，不生成真机 PASS。
- 比较实际 fingerprint 的 ID、增量号、版本、类型和标签。
- 对照 sensorservice 注册类型与 PackageManager features，不按数量评分。
- 读取 SurfaceFlinger 的实际 GLES 行，标出报告中的软件渲染路径。
- 结构化解析 proc mountinfo，保留独立文件挂载证据，不将路径存在直接判为隐藏。
- 输出始终包含 `trust_verdict=not_evaluated`、`cts_verdict=not_run`。
- 输出不包含完整原始 dump、设备序列号或 MAC；本地证据文件不覆盖。

运行入口：

```bash
bash tools/audit-fingerprint.sh \
  --adb /absolute/path/to/adb --serial 127.0.0.1:15555 \
  --json --output /existing/directory/new-audit.json
```

退出码：0 为本次采样的检查一致；1 为发现差异；2 为不完整、读取或输入错误。
任何退出码都不代表 CTS/设备信任结论。入口通过 `bash` 调用，不依赖文件执行位。

本次真实运行：0 条命令错误，2 类 `different`，9 条 `observed`：

1. fingerprint 中的 `BP4A.260205.001/13561507` 与实际
   `BP4A.251205.006/20260908` 不一致。
2. ambient_temperature、barometer、hinge_angle、light、proximity、
   relative_humidity 对应 sensor 类型存在而 feature 缺失。

这两项的镜像源码修复已在 [构建与传感器契约](BUILD_SENSOR_CONTRACT.md) 中落实。
本次增加运行时验收，不能据此声称旧 VM 已更新。

### 2. 修复旧 UI Automator 的类路径

系统自带 `uiautomator runtest` 可复现：

```text
NoClassDefFoundError: Failed resolution of: Landroid/test/RepetitiveTest;
```

工具甚至同时打印 `OK (1 test)`，因此不能只根据命令返回码或 OK 子串判断测试成功。
`patches/0022-uiautomator-include-test-base-dependency.patch` 为
frameworks/base 中的 shell 入口补充 `android.test.base.jar` 和
`android.test.mock.jar`，已接入补丁链和增量构建源文件恢复。

验证使用原脚本的临时副本 `/data/local/tmp/uiautomator-validated.sh`：
修复后无需手动传入依赖 jar，真实控件滚动测试完成，
`UI_ACTION_COMPLETE`、测试状态 0、`OK (1 test)` 同时出现。
没有覆盖 `/system/bin/uiautomator`。一次此前的“label not found”是页面控件不可见，
独立保留其失败日志，未计为通过。

这个修复解决测试工具启动故障，**没有证据说明它会修复 Risk Detector 的 CTS Check 1**。

## 验证与剩余工作

- 58 项 Python 回归通过。
- 补丁 0022 对 LineageOS `lineage-23.2` 脚本应用通过。
- wrapper 的 dump、绝对/相对 jar、`--nohup` 主机测试通过。
- 补丁脚本在 ARM64 来宾临时路径执行通过；新版审计在该来宾实际完成。
- 相关 shell 语法、补丁和 diff 检查通过。
- 本机没有完整 Linux Android 构建树，没有重编译/部署新镜像或发布版本。

仍需用新镜像复测构建元数据和 sensor 列表。`CTS Check 1`、Framework Patch
需要检测器规则说明或可对应到具体断言的官方 CTS 失败记录，才能开展有依据的修复。
ADB、LineageOS 和 unlocked 状态属于实际配置/来源，不做隐藏或改判处理。
锁屏凭据属于用户设置，没有为了去掉标签自动设置密码。

## 证据

原始证据保存在本地：
`/Users/bytedance/Project/qemu-android-arm64/artifacts/riskdetector-1.4-20260914/`。
目录权限为 0700；截图/XML 可能包含应用读取的标识符，未提交到 Git。

- `apk-signature.txt`、`manifest.txt`、`install.txt`、`launch.txt`
- `basic-utm-click-20260915.*`、`basic-a11y-scroll-20260915.*`
- `risk-apps-20260916.*`、`risk-apps-rest-20260916.*`
- `riskinfo-top-20260915.*`、`riskinfo-bottom-20260915.*`
- `cts-open-20260915.*`、`risks-top-20260915.*`、`risks-open-20260915.*`
- `device-info-20260916.*`、`final-overview-20260916.*`
- `detector-mountinfo-20260916.txt`、`proc-observations-20260916.txt`
- `runtime-audit-20260916.json`、`unit-tests-20260916.log`
- `scroll-action.txt`（原始类路径异常）、`uiautomator-patched-pass.txt`

原始检测器日志中的反射 KeyStore 调用异常无法归属到某个编号规则，不能据此
宣称完成漏洞复现。本文只引用核对所需的非敏感值。
