# 纸上管家 paperbutler · 智能设备局域网控制桥

基于 `python-miio` 的局域网直连方案：不依赖厂商云 / Home Assistant，直接向设备发 miIO 指令；同时提供一套轻量 HTTP API，供没有 UDP 能力的设备（如 Lua 沙箱）接入。

> **纸上管家（paperbutler）** 与 ESP32 端同名应用配套：设备侧应用通过本桥的 HTTP API 控制局域网设备；本服务也可独立使用（自带网页控制台）。名字来源：paper（纸）+ butler（管家）。

> **许可证：GPL-3.0-only**（强 copyleft，强制开源）。全文见 [LICENSE](LICENSE)，第三方声明见 [NOTICE](NOTICE)。
>
> **非关联声明 / Disclaimer**：与上游 `python-miio` 一样，本项目是自愿的、社区驱动的努力（*a voluntary, community-driven effort*），与被支持设备的任何公司均无关联（*is not affiliated with any of the companies whose devices are supported by this project*）。本项目为非官方第三方工具，商标仅作事实性描述，不构成背书、赞助或关联。

## 这个仓库里有什么 / 没有什么

```
paperbutler/                        （作为 git 仓库根目录）
├── app.py                      # Flask 服务：网页控制台 + HTTP 桥
├── templates/index.html        # 前端页面
├── requirements.txt            # 运行必需依赖（仅 2 个包）
├── devices.example.json        # 设备配置模板（全部为占位符，可提交）
├── API.md                      # HTTP 桥接口契约（供设备侧接入）
├── LICENSE                     # GNU GPLv3 全文
├── NOTICE                      # 第三方组件、许可证与版权声明
├── README.md                   # 本文件
├── setup.sh                    # 一键部署脚本
└── .gitignore                  # 排除本地凭据、虚拟环境与按需下载的工具
```

**特意没有放进仓库的**：`.venv/`、`token-extractor/`、`devices.json`、`tokens.json`、`__pycache__/`。原因与获取方式见文末「非强制依赖」。

## 快速开始

### 方式 A：部署脚本（推荐）

```bash
./setup.sh                          # 只装运行必需依赖
./setup.sh --with-token-extractor   # 额外下载 token 导出工具（首次配置时需要）
```

脚本会：创建 `.venv` → 安装 `requirements.txt` → 从模板生成 `devices.json` →（可选）clone 并配置 token 导出工具。所有生成物都被 `.gitignore` 排除，不会污染仓库。脚本非交互，可直接在 CI / 新机器上跑。

### 方式 B：手动

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp devices.example.json devices.json
```

## 获取设备 token（配置期可选步骤）

只在首次配置或 token 失效时需要。`Xiaomi-cloud-tokens-extractor`（MIT）**不随本仓库分发**，两种方式获取：

```bash
# 方式 A：脚本
./setup.sh --with-token-extractor

# 方式 B：手动（去人家仓库下载工具）
git clone --depth 1 https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor.git token-extractor
python3 -m venv token-extractor/.venv
token-extractor/.venv/bin/pip install -r token-extractor/requirements.txt
cd token-extractor && .venv/bin/python token_extractor.py -s cn -o tokens.json
```

按提示扫码登录（中国大陆区域 `-s cn`），导出账号下设备的 IP / token / model，填入 `devices.json`。token 是从云端拉取的，但**控制时完全走局域网**。token 在设备重置配网、部分固件升级后会变，届时重新导出。

## 填写 devices.json

> **填写前先获取 token**：需要先从第三方工具仓库 [`Xiaomi-cloud-tokens-extractor`](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) 下载工具，登录自己的账号导出设备的 IP 与 token，再填到 `devices.json`。具体命令见上方「获取设备 token」。

`devices.json` 由模板复制而来，**必须把下面这些占位符全部替换**：

| 占位符                           | 换成                       | 说明                     |
| ----------------------------- | ------------------------ | ---------------------- |
| `<REPLACE_WITH_32_HEX_TOKEN>` | 32 位十六进制字符串              | 设备 token，用导出工具从自己的账号获取 |
| `<DEVICE_LAN_IP>`             | 设备实际的局域网 IPv4 地址字符串      | 建议 DHCP 保留 / 静态 IP     |
| `<EXAMPLE_LAN_IP>`            | 同上                       | 模板里其它示例设备的 IP          |
| `<BRIDGE_HOST_IP>`            | 运行本服务那台主机的局域网 IPv4 地址字符串 | 设备侧访问用                 |

> token 必须是 32 位合法十六进制。若保留占位符不改，`GET /devices` 仍能返回列表，但状态/控制接口会给出「token 缺失或长度不对」的友好提示。  
> `devices.json` 含真实凭据，已由 `.gitignore` 排除，**不要提交、不要分享**。

`type` 三种取值：`yeelight`、`chuangmi_plug` / `plug`、`miot`。现代 MIoT 设备需在 `mapping` 写明 siid/piid（按自己型号从 miot-spec.org 查）；写了哪些属性，页面上就出现哪些控件。动作型设备（如电饭煲）用 `actions` / `options` / `value_labels` 配置，示例见模板。

## 启动

```bash
.venv/bin/python app.py
```

- 本机网页控制台：<http://127.0.0.1:9090>
- 设备侧访问地址：`http://<BRIDGE_HOST_IP>:9090`（替换为实际主机 IP；**必须用 `http://`**，设备端自签证书在 https 下一律校验失败）

服务监听 `0.0.0.0:9090`。设备与本机需在同一 IPv4 网段，关闭 AP / 访客网络隔离。

## 非强制依赖：为什么没放进仓库

| 部件                                   | 用途          | 为何不内置                              | 如何获得                                       |
| ------------------------------------ | ----------- | ---------------------------------- | ------------------------------------------ |
| `.venv/`                             | Python 虚拟环境 | 本地安装产物，不是源码，体积大且与平台绑定              | `setup.sh` 或 `python3 -m venv .venv`       |
| `token-extractor/`                   | 仅首次导出 token | 第三方 MIT 仓库，运行服务不需要；内置会带来额外的第三方分发义务 | `setup.sh --with-token-extractor` 或上面的手动命令 |
| `devices.json`                       | 你的真实配置      | 含 token / 内网 IP / MAC，属敏感凭据        | 从 `devices.example.json` 复制并填写             |
| `tokens.json`、`__pycache__/`、`*.pyc` | 导出结果 / 缓存   | 凭据或构建产物，与源码无关                      | 自动生成，已 gitignore                           |

**结论**：运行本项目只需要 `requirements.txt` 里的两个包；token 导出工具是「配置期」的可选工具。仓库同时提供了自动部署脚本和完全手动的命令，两条路都能走通。若你把 `token-extractor/` 连同本仓库一起再分发，需保留其 MIT LICENSE 与版权声明（见 `NOTICE`）。同理，再分发本仓库时须保留 `python-miio` 的 GPLv3 全文（本仓库根目录 `LICENSE`）与 `NOTICE` 中的全部第三方声明。

## HTTP 桥接口

```
GET  /devices                  设备列表（含 capabilities / actions / options / value_labels）
GET  /devices/{id}/status      状态
POST /devices/{id}/set         开关 / 属性写入（按 capabilities 校验）
POST /devices/{id}/action      动作型设备（如开始 / 取消烹饪）
```

完整字段、能力校验、模式取值与 Lua 沙箱侧约束见 [API.md](API.md)。

## 注意

- 设备与本机同网段；给设备设静态 IP 或 DHCP 保留，IP 变了连不上。
- 设备固件更新可能导致 token 变化，变化后需重新导出并更新 `devices.json`。
- Zigbee / 蓝牙 Mesh 子设备没有独立 token，本方案不适用（只有网关有）。
- 示例只提供了灯和电饭煲的 demo 示范；其余设备需要用户自行适配拓展。

## 许可与合规

本项目采用 **GNU General Public License, version 3 only（GPL-3.0-only）** 授权，完整文本见 [LICENSE](LICENSE)。

**为什么是 GPLv3**：核心库 `python-miio` 以 `GPL-3.0-only` 发布，本项目运行时链接它构成组合作品，因此分发时必须整体以 GPLv3 提供。本项目未修改 python-miio 源码，仅通过 `requirements.txt` 安装并 `import miio`。

- 可自由运行、修改、再分发（含商业使用）；再分发时必须保留版权与许可证声明、附 GPLv3 全文、以 GPL-3.0-only 提供完整对应源代码，且不得附加额外限制。
- 软件按「现状」提供，**无任何担保**（LICENSE §15–§16）。
- 第三方组件与版权声明见 [NOTICE](NOTICE)；依赖树中的 MIT / BSD / Apache-2.0 / LGPL / MPL 组件与 GPLv3 兼容。
- **商标**：「米家」「Mijia」「Xiaomi」「MIoT」为小米公司商标，此处仅作事实性描述（nominative fair use），不构成背书、赞助或关联。

> 仅在自己设备上运行、不向他人交付软件拷贝时，GPLv3 的分发义务不触发。本仓库仍按上述条款开放。

## 第三方归属汇总

| 组件 | 许可证 | 版权 |
| --- | --- | --- |
| python-miio 0.5.12 | GPL-3.0-only | Teemu R (tpr@iki.fi) 及 python-miio 贡献者 |
| Flask 3.1.3 | BSD-3-Clause | Copyright (c) 2010 Pallets |
| Xiaomi-cloud-tokens-extractor（不随仓库分发） | MIT | Copyright (c) 2020 Piotr Machowski |

完整清单（含间接依赖）见 [NOTICE](NOTICE)。
