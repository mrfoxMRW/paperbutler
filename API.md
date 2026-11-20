<!-- SPDX-License-Identifier: GPL-3.0-only -->

# 纸上管家 · 局域网控制桥 HTTP API 契约

## 基本信息

| 项 | 值 |
|---|---|
| 服务地址 | `http://<BRIDGE_HOST_IP>:9090` |
| 协议 | HTTP/1.1（**必须用 http://，不要用 https://**，设备端自签证书会校验失败） |
| 数据格式 | 全部 `application/json; charset=utf-8` |
| 认证 | 无（仅限局域网使用） |
| 响应体上限 | 远小于 131072 字节（列表接口不探测设备，秒回） |
| 超时建议 | 单次请求 3~5 秒 |

> `<BRIDGE_HOST_IP>` 是字符串占位符，请替换为运行本服务那台主机的局域网 IP。本仓库文档与配置里所有 `<...>` 都需按实际环境替换；若主机换网络导致 IP 变化，要同步更新设备侧配置。

---

## 接口 1：查询设备列表

```
GET /devices
```

只读本地配置，**不访问设备**，可立即返回。

响应（当前两台设备，`cooker1` 展示动作型设备的完整元数据）：

```json
{
  "ok": true,
  "count": 2,
  "devices": [
    {
      "id": "d1",
      "name": "示例插座",
      "type": "miot",
      "capabilities": ["power"],
      "actions": [],
      "action_labels": {},
      "options": {},
      "value_labels": {}
    },
    {
      "id": "cooker1",
      "name": "示例电饭煲",
      "type": "miot",
      "capabilities": [],
      "actions": ["start_cook", "cancel_cooking"],
      "action_labels": {
        "start_cook": "开始烹饪",
        "cancel_cooking": "取消烹饪"
      },
      "options": {
        "cook_mode": [
          {"value": 2, "label": "精煮饭"},
          {"value": 1, "label": "快煮饭"},
          {"value": 3, "label": "煮粥"},
          {"value": 4, "label": "保温"},
          {"value": 5, "label": "自定义"}
        ]
      },
      "value_labels": {
        "status": {"1":"待机中","2":"烹饪中","3":"预约中","4":"保温中","5":"设备异常","6":"固件升级中","7":"烹饪已完成"},
        "cook_mode": {"1":"快煮饭","2":"精煮饭","3":"煮粥","4":"保温","5":"自定义"}
      }
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | bool | 是否成功 |
| `count` | int | 设备数量 |
| `devices[].id` | string | **设备唯一 ID，后续接口用它**，纯 ASCII 短串 |
| `devices[].name` | string | 显示名称（UTF-8） |
| `devices[].type` | string | `miot` / `yeelight` / `chuangmi_plug` |
| `devices[].capabilities` | string[] | 属性能力：`power`、`brightness`、`color_temp`；**当前 `d1`=["power"]，`cooker1`=[]** |
| `devices[].actions` | string[] | 动作列表（动作型设备才有），如 `start_cook`、`cancel_cooking` |
| `devices[].action_labels` | object | 动作名 → 中文标签，直接用作按钮文字 |
| `devices[].options` | object | 可选项列表，如 `options.cook_mode`，**设备端渲染模式按钮就用这个** |
| `devices[].value_labels` | object | 属性值 → 中文标签，把状态接口读回来的数字翻成中文 |

> 动作型设备（如电饭煲）没有 `capabilities`，靠 `actions` + `action_labels` + `options` + `value_labels` 渲染界面。
>
> `options.cook_mode` 是「有哪些模式可以选」，`value_labels.cook_mode` 是「读回来的数字显示成什么」，两者用途不同，不要混用。
>
> `options` 与 `devices.json` 同步，改完配置刷新 `GET /devices` 即可生效，**不需要重启服务**。

---

## 接口 2：查询设备状态

```
GET /devices/{id}/status
```

会真实访问设备（UDP miIO），正常 0.1~1 秒。

开关类设备（请求 `GET /devices/d1/status`）：

```json
{"ok": true, "power": false}
```

只有 `capabilities` 含 `brightness` / `color_temp` 的**灯类设备**才会多出这两个字段，例如：

```json
{"ok": true, "power": true, "brightness": 60, "color_temp": 4000}
```

> ⚠️ **当前接入的两台设备都不支持亮度/色温**：`d1` 是 `cuco.plug.v3` 插座（`capabilities` 只有 `power`），`cooker1` 是电饭煲（动作型设备，`capabilities` 为 `[]`）。
> 上面这个 `4000K` 只是「将来如果接了灯」的契约示例，**不是当前设备的真实字段**，设备端别照着渲染。一切以 `GET /devices` 返回的 `capabilities` 为准。

动作型设备（请求 `GET /devices/cooker1/status`，实测返回）：

```json
{"ok": true, "status": 1, "status_label": "待机中", "fault": 0}
```

- `xxx_label` 字段由 `value_labels` 自动生成，可直接显示，设备端不必再内置一份中文表。
- `status` 状态值：1 待机中 / 2 烹饪中 / 3 预约中 / 4 保温中 / 5 设备异常 / 6 固件升级中 / 7 烹饪已完成。
- `fault`：`0` = 无故障；非 0 为故障码。

> ⚠️ **待机时读不到 `cook_mode` 是正常的**：设备对该属性返回 `code: -4001`，本接口会直接省略该字段（上述实测响应里就没有 `cook_mode`）。
> 所以**不要用状态接口里的 `cook_mode` 去渲染模式选择器**，一律以 `GET /devices` 的 `options.cook_mode` 为准；模式值由设备端自己记住用户上次选了哪个。

失败响应（500）：

```json
{"ok": false, "error": "设备无响应：确认设备在线、IP 正确、与本机同网段"}
```

设备不存在（404）：

```json
{"ok": false, "error": "找不到该设备"}
```

---

## 接口 3：控制设备（开关 / 属性；亮度色温仅灯类设备）

```
POST /devices/{id}/set
Content-Type: application/json
```

**五种请求体写法，任选其一**（按优先级匹配）：

```json
{"power": true}                          // 直接设开关（bool）
{"action": "on"}                         // 或 off / toggle（字符串）
{"brightness": 60}                       // 仅灯类：设亮度 1~100
{"color_temp": 4000}                     // 仅灯类：设色温约 2700~6500
{"property": "cook_mode", "value": 4}    // 通用属性写入：选模式（4=保温，见下方模式表）
```

> 带 `brightness` / `color_temp` 的两行是**为将来接灯预留的契约**，当前两台设备都不支持；给电饭煲发 `{"color_temp":4000}` 会直接被 400 拦下（见下方「能力校验」）。
> 模式选择若只是改配置、不立刻开火，用 `property` 写法；若要「选好模式并立刻开始」，直接用接口 4 把模式放进 `params`。

### 能力校验

`/devices/{id}/set` 会先按 `capabilities` 校验，**不支持的字段直接返回 400，不会把指令发到设备**：

```json
{"ok": false, "error": "该设备不支持 color_temp；可用 capabilities: []"}
```

`property` 也必须是 `mapping` 里定义过的键，否则同样 400：

```json
{"ok": false, "error": "属性 foo 未在 mapping 中定义"}
```

成功响应（200）：

```json
{"ok": true, "state": {"power": true}}
```

失败响应（500 / 400 / 404）：

```json
{"ok": false, "error": "错误说明"}
```

---

## 接口 4：调用动作（动作型设备，如电饭煲）

```
POST /devices/{id}/action
Content-Type: application/json
```

请求体：

```json
{"action": "start_cook", "params": [{"piid": 5, "value": 2}]}
```

- `action`：动作名，从 `/devices` 的 `actions` 字段取（如 `start_cook`、`cancel_cooking`）
- `params`：动作入参，MIoT 格式 `[{"piid":5,"value":模式值}]`；**可省略**，省略时用配置里的默认入参（默认 `2 精煮饭`）

成功响应（200）：

```json
{"ok": true, "action": "start_cook", "state": {"status": 2, "status_label": "烹饪中", "fault": 0}}
```

电饭煲动作说明（`chunmi.cooker.c301`，`siid=2`）：

| 动作名 | aiid | 含义 | 入参 |
|---|---|---|---|
| `start_cook` | 1 | 开始烹饪 | `piid=5` 模式值，见下方模式表（1/2/3/4/5） |
| `cancel_cooking` | 2 | 取消烹饪 | 无，`params` 传 `[]` 或省略 |

> 该接口会**真的让电饭煲开始加热**，属物理动作，联调时请用 `cancel_cooking` 或先确认锅内有米有水。

---

## 小饭煲模式列表（`cook_mode` · siid=2 / piid=5）

来源：MIoT 规格 `urn:miot-spec-v2:device:cooker:0000A00B:chunmi-c301:1` 的「烹饪模式」属性与「开始烹饪」入参定义。

| 值 | 模式 | 说明 |
|---|---|---|
| `1` | 快煮饭 | 快速程序 |
| `2` | 精煮饭 | **默认模式**（配置里 `start_cook.in` 的默认值） |
| `3` | 煮粥 | — |
| `4` | **保温** | 官方规格里的合法值，**本次新补进 `options` 和本文档** |
| `5` | 自定义 | 需要设备里已存在自定义食谱 |

三种使用方式：

```bash
# 1) 渲染模式按钮：以 /devices 返回的 options.cook_mode 为准
GET /devices
# -> devices[1].options.cook_mode = [{value:2,label:"精煮饭"},...,{value:4,label:"保温"},...]

# 2) 只写模式属性、不启动
POST /devices/cooker1/set
{"property": "cook_mode", "value": 4}

# 3) 带着模式启动烹饪
POST /devices/cooker1/action
{"action": "start_cook", "params": [{"piid": 5, "value": 4}]}
```

补充注意：

- `4 保温` 在规格上属于 `cook-mode` 的合法取值，但部分固件可能**拒绝用 4 直接调用 `start_cook`**（保温通常是烹饪结束后自动进入的状态，而非独立烹饪程序）。若接口报错，改用 `1/2/3/5` 启动，保温让设备自行进入；`set` 写属性一般不受影响。
- `5 自定义` 在没有自定义食谱时可能返回错误。
- 之前文档只写了 `1/2/3/5`，漏了 `4 保温`；现已同步修正 `devices.json`、`devices.example.json`、`API.md` 三处，`/devices` 的 `options` 也会多出「保温」按钮。

---

## 当前设备

| id | 名称 | 型号 | 能力 |
|---|---|---|---|
| `d1` | 示例插座 | cuco.plug.v3（MIoT 插座） | 开关（实测通过） |
| `cooker1` | 示例电饭煲 | chunmi.cooker.c301 | 状态读取（实测通过）+ 5 种模式选择 + 开始/取消烹饪 |

---

## 接入侧（Lua 沙箱）注意事项

1. **同一时刻只能有一个请求未完成**，第二个返回 busy；在 `ctx:after` 完成回调里再排下一个请求，不要并发。
2. `ctx.net:request` 的 url 直接写 `http://<BRIDGE_HOST_IP>:9090/devices`，无需公网域名。
3. POST 请求带 `Content-Type: application/json`，body 是 JSON 字符串。
4. 单次回调 1 秒限制：列表接口瞬时返回；状态/控制接口正常 0.1~1 秒，若偶发超时按 busy/失败处理并重试一次即可。
5. `manifest.permissions` 需包含 `"net"`。
6. 频繁轮询时用 `keep_wifi(-1)` 保持连接，手动刷新时才用默认 5 分钟。
7. Studio 预览页是 https，浏览器会禁止访问 http 局域网地址，**必须在真机上验证**。

---

## 接入流程（四步）

```
GET /devices                  -> 拿 id、capabilities、actions、action_labels、options、value_labels，渲染卡片
GET /devices/{id}/status      -> 刷新状态（power / status + xxx_label / fault）
POST /devices/{id}/set        -> 开关 / 滑杆 / 模式属性写入，用返回的 state 更新卡片
POST /devices/{id}/action     -> 动作型设备：开始烹饪（带模式）/ 取消烹饪
```

> 渲染规则：
> - `capabilities` 含 `power` → 显示开关；含 `brightness`/`color_temp` → 显示滑杆（**当前两台设备都没有这两个能力，不要渲染滑杆**）。
> - 有 `actions` → 显示状态文本（取 `xxx_label`）+ 模式按钮（遍历 `options.cook_mode` 的 `value`/`label`，默认选中 `2`）+ 动作按钮（文字取 `action_labels`）。
> - 点「开始烹饪」时，把当前选中的模式值组装成 `params: [{"piid":5,"value":模式值}]` 传给接口 4。

---

## 声明

本接口与项目均为非官方社区实现，与上游 `python-miio` 一样，是自愿的、社区驱动的努力，与被支持设备的任何公司均无关联。商标仅作事实性描述，不构成背书、赞助或关联。软件按「现状」提供，无任何担保；许可证 GPL-3.0-only。
