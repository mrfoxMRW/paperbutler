# 纸上管家 paperbutler - 智能设备局域网控制桥
# Copyright (C) 2026 The paperbutler Authors
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""纸上管家 paperbutler：智能设备局域网控制桥，基于 python-miio 的局域网直连方案。

不联网、不依赖厂商云 / Home Assistant。设备 IP + token 由
Xiaomi-cloud-tokens-extractor 从账号导出后填入 devices.json。

启动：
    .venv/bin/python app.py
然后浏览器打开 http://127.0.0.1:9090
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

log = logging.getLogger("paperbutler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent
DEVICES_FILE = BASE_DIR / "devices.json"

app = Flask(__name__)


# ---------------------------------------------------------------------------
# 设备控制器：把不同协议的灯统一成 status / set_power / set_brightness /
# set_color_temp 四个动作，Web 层无需关心底层差异。
# ---------------------------------------------------------------------------
class BaseController:
    capabilities: set[str] = set()

    def __init__(self, cfg: dict[str, Any]):
        self.name = cfg["name"]
        self.cfg = cfg

    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    def set_power(self, on: bool) -> None:
        raise NotImplementedError

    def set_brightness(self, value: int) -> None:
        raise NotImplementedError

    def set_color_temp(self, value: int) -> None:
        raise NotImplementedError

    def call_action(self, name: str, params=None):
        """动作型设备（如电饭煲的开始/取消烹饪）覆写此方法。"""
        raise NotImplementedError(f"该设备不支持动作: {name}")

    def close(self) -> None:
        pass


class YeelightController(BaseController):
    """Yeelight 灯泡 / 灯带（老 miIO 协议，自带亮度、色温）。"""

    capabilities = {"power", "brightness", "color_temp"}

    def __init__(self, cfg):
        super().__init__(cfg)
        from miio import Yeelight

        self.dev = Yeelight(cfg["ip"], cfg["token"], model=cfg.get("model"))

    def status(self):
        s = self.dev.status()
        return {
            "power": bool(s.is_on),
            "brightness": getattr(s, "brightness", None),
            "color_temp": getattr(s, "color_temp", None),
        }

    def set_power(self, on):
        self.dev.on() if on else self.dev.off()

    def set_brightness(self, value):
        self.dev.set_brightness(int(value))

    def set_color_temp(self, value):
        self.dev.set_color_temp(int(value))


class PlugController(BaseController):
    """WiFi 智能插座 / 开关面板（chuangmi.plug.* 等）。"""

    capabilities = {"power"}

    def __init__(self, cfg):
        super().__init__(cfg)
        from miio import ChuangmiPlug

        self.dev = ChuangmiPlug(cfg["ip"], cfg["token"], model=cfg.get("model"))

    def status(self):
        s = self.dev.status()
        return {"power": bool(s.is_on)}

    def set_power(self, on):
        self.dev.on() if on else self.dev.off()


class MiotController(BaseController):
    """通用 MIoT 设备：属性读写 + 动作调用。

    配置里的 mapping 用 key 区分：
      - 属性 key（power/brightness/color_temp/status/任意自定义名）：含 siid/piid
      - 动作 key：含 siid/aiid（可带 in 参数定义）
    这样同一套控制器既能控灯、插座，也能控电饭煲这类动作型设备。
    """

    PROPERTY_CAPS = {"power", "brightness", "color_temp"}

    def __init__(self, cfg):
        super().__init__(cfg)
        from miio import MiotDevice

        self.mapping = cfg.get("mapping") or {}
        self.actions = cfg.get("actions") or {}
        self.value_labels = cfg.get("value_labels") or {}
        # 属性类能力（供前端渲染控件）
        self.capabilities = set(self.mapping.keys()) & self.PROPERTY_CAPS
        # 动作也算一种能力，前端据此渲染动作按钮
        self.action_names = list(self.actions.keys())
        if not self.capabilities and not self.action_names:
            raise ValueError("MIoT 设备缺少 mapping 或 actions 配置")
        self.dev = MiotDevice(
            cfg["ip"], cfg["token"], mapping=self.mapping, model=cfg.get("model")
        )

    def status(self):
        if not self.mapping:
            return {}
        raw = self.dev.get_properties_for_mapping()
        result = {}
        for item in raw or []:
            if not isinstance(item, dict) or item.get("code") != 0:
                continue
            key = item.get("did")
            if key not in self.mapping:
                continue
            val = item.get("value")
            # 布尔属性转 bool
            if key == "power":
                val = bool(val)
            result[key] = val
            # 若有中文标签映射，附加一个 xxx_label 字段
            if key in self.value_labels and str(val) in self.value_labels[key]:
                result[f"{key}_label"] = self.value_labels[key][str(val)]
        return result

    def set_power(self, on):
        self.dev.set_property("power", bool(on))

    def set_brightness(self, value):
        self.dev.set_property("brightness", int(value))

    def set_color_temp(self, value):
        self.dev.set_property("color_temp", int(value))

    def set_property(self, key, value):
        """通用属性写入（用于模式选择等非标属性）。"""
        if key not in self.mapping:
            raise KeyError(f"属性 {key} 未在 mapping 中定义")
        self.dev.set_property(key, value)

    def call_action(self, name: str, params=None):
        """调用动作。actions 配置形如 {start_cook: {siid:2, aiid:1, in:[{piid:5}]}}。"""
        if name not in self.actions:
            raise NotImplementedError(f"该设备不支持动作: {name}")
        action = self.actions[name]
        siid, aiid = action["siid"], action["aiid"]
        # params 可由调用方覆盖；否则用配置里的默认入参（带当前选择的值）
        final_params = params if params is not None else action.get("in", [])
        return self.dev.call_action_by(siid, aiid, final_params)


CONTROLLERS = {
    "yeelight": YeelightController,
    "chuangmi_plug": PlugController,
    "plug": PlugController,
    "miot": MiotController,
}


def capabilities_of(cfg: dict[str, Any]) -> set[str]:
    """从配置推导设备支持的「可控属性」能力，供 /devices 下发与 /set 入参校验共用。

    只包含 power / brightness / color_temp；status、fault、cook_mode 这类只读或
    自定义属性不算能力，动作型设备由 actions 区分，capabilities 会是空集。
    """
    dev_type = cfg.get("type")
    if dev_type == "yeelight":
        return {"power", "brightness", "color_temp"}
    if dev_type in ("plug", "chuangmi_plug"):
        return {"power"}
    if dev_type == "miot":
        return set((cfg.get("mapping") or {}).keys()) & MiotController.PROPERTY_CAPS
    return set()


def load_devices() -> list[dict[str, Any]]:
    if not DEVICES_FILE.exists():
        return []
    data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    return data.get("devices", [])


def build_controller(cfg: dict[str, Any]) -> BaseController:
    dev_type = cfg.get("type", "miot")
    cls = CONTROLLERS.get(dev_type)
    if cls is None:
        raise ValueError(f"未知设备类型: {dev_type}")
    token = str(cfg.get("token") or "")
    if len(token) != 32:
        raise ValueError(f"token 缺失或长度不对（应为32位十六进制），当前 {len(token)} 位")
    try:
        bytes.fromhex(token)
    except ValueError:
        raise ValueError("token 不是合法的十六进制字符串")
    return cls(cfg)


# ---------------------------------------------------------------------------
# Web 路由
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    configured = DEVICES_FILE.exists()
    return render_template("index.html", configured=configured)


@app.route("/api/devices")
def api_devices():
    cfgs = load_devices()
    result = []
    for cfg in cfgs:
        entry = {
            "name": cfg.get("name", "未命名"),
            "type": cfg.get("type"),
            "ip": cfg.get("ip"),
            "error": None,
            "state": None,
            "capabilities": [],
        }
        try:
            ctrl = build_controller(cfg)
            entry["capabilities"] = sorted(ctrl.capabilities)
            entry["state"] = ctrl.status()
        except Exception as exc:  # 连接失败、token 错误等，逐台隔离
            log.warning("读取设备 %s 状态失败: %s", entry["name"], exc)
            entry["error"] = friendly_error(exc)
        finally:
            try:
                ctrl.close()
            except Exception:
                pass
        result.append(entry)
    return jsonify(result)


@app.route("/api/control/<name>", methods=["POST"])
def api_control(name: str):
    cfgs = load_devices()
    cfg = next((c for c in cfgs if c.get("name") == name), None)
    if cfg is None:
        return jsonify({"ok": False, "error": "找不到该设备"}), 404

    payload = request.get_json(silent=True) or {}
    ctrl = None
    try:
        ctrl = build_controller(cfg)
        action = payload.get("action")
        caps = capabilities_of(cfg)
        need = {"power": "power", "toggle": "power",
                "brightness": "brightness", "color_temp": "color_temp"}.get(action)
        if need and need not in caps:
            return jsonify({
                "ok": False,
                "error": f"该设备不支持 {need}；可用 capabilities: {sorted(caps) or '[]'}",
            }), 400

        if action == "power":
            ctrl.set_power(bool(payload.get("value")))
        elif action == "toggle":
            current = ctrl.status().get("power", False)
            ctrl.set_power(not current)
        elif action == "brightness":
            ctrl.set_brightness(payload["value"])
        elif action == "color_temp":
            ctrl.set_color_temp(payload["value"])
        else:
            return jsonify({"ok": False, "error": f"未知动作: {action}"}), 400

        return jsonify({"ok": True, "state": ctrl.status()})
    except KeyError as exc:
        return jsonify({"ok": False, "error": f"缺少参数: {exc}"}), 400
    except Exception as exc:
        log.exception("控制设备 %s 失败", name)
        return jsonify({"ok": False, "error": friendly_error(exc)}), 500
    finally:
        if ctrl is not None:
            try:
                ctrl.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 给 Lua 沙箱设备用的轻量 HTTP 桥接口
# 设备端没有 UDP，无法直连 miIO，因此由本服务代为说 miIO，对外只暴露 HTTP。
# 设计约束（来自设备端契约）：响应体 < 131072 字节、单次回调 1 秒。
#   GET  /devices              -> 设备列表（只读配置，不探测设备，秒回）
#   GET  /devices/<id>/status  -> 设备状态
#   POST /devices/<id>/set     -> 控制（power / brightness / color_temp / property）
#   POST /devices/<id>/action  -> 动作型设备（开始/取消烹饪，带模式入参）
# ---------------------------------------------------------------------------
def device_id_of(cfg: dict[str, Any], index: int) -> str:
    """优先用配置里显式写的 id；否则按序号生成 dev1/dev2（纯 ASCII，便于拼 URL）。"""
    return str(cfg.get("id") or f"dev{index + 1}")


def find_by_id(device_id: str):
    for i, cfg in enumerate(load_devices()):
        if device_id_of(cfg, i) == str(device_id):
            return cfg
    return None


@app.route("/devices")
def bridge_devices():
    result = []
    for i, cfg in enumerate(load_devices()):
        # 元数据直接从配置读，即使 token 缺失也能渲染界面（状态接口会给出提示）
        caps = sorted(capabilities_of(cfg))
        actions = list((cfg.get("actions") or {}).keys())
        result.append({
            "id": device_id_of(cfg, i),
            "name": cfg.get("name", "未命名"),
            "type": cfg.get("type"),
            "capabilities": caps,
            "actions": actions,
            "value_labels": cfg.get("value_labels", {}),
            "options": cfg.get("options", {}),
            "action_labels": {
                k: v.get("label", k) for k, v in (cfg.get("actions") or {}).items()
            },
        })
    return jsonify({"ok": True, "count": len(result), "devices": result})


@app.route("/devices/<device_id>/status")
def bridge_status(device_id: str):
    cfg = find_by_id(device_id)
    if cfg is None:
        return jsonify({"ok": False, "error": "找不到该设备"}), 404
    ctrl = None
    try:
        ctrl = build_controller(cfg)
        return jsonify({"ok": True, **ctrl.status()})
    except Exception as exc:
        log.warning("读取设备 %s 状态失败: %s", device_id, exc)
        return jsonify({"ok": False, "error": friendly_error(exc)}), 500
    finally:
        if ctrl is not None:
            try:
                ctrl.close()
            except Exception:
                pass


@app.route("/devices/<device_id>/set", methods=["POST"])
def bridge_set(device_id: str):
    cfg = find_by_id(device_id)
    if cfg is None:
        return jsonify({"ok": False, "error": "找不到该设备"}), 404

    payload = request.get_json(silent=True) or {}
    caps = capabilities_of(cfg)

    # 先按 capabilities 校验：电饭煲/插座不该收到亮度、色温这类灯的参数
    need = None
    if "power" in payload or "action" in payload:
        need = "power"
    elif "brightness" in payload:
        need = "brightness"
    elif "color_temp" in payload:
        need = "color_temp"
    if need and need not in caps:
        return jsonify({
            "ok": False,
            "error": f"该设备不支持 {need}；可用 capabilities: {sorted(caps) or '[]'}",
        }), 400
    if "property" in payload:
        key = payload["property"]
        if not isinstance(key, str) or key not in (cfg.get("mapping") or {}):
            return jsonify({"ok": False, "error": f"属性 {key} 未在 mapping 中定义"}), 400

    ctrl = None
    try:
        ctrl = build_controller(cfg)
        if "power" in payload:
            ctrl.set_power(bool(payload["power"]))
        elif "action" in payload:
            act = str(payload["action"]).lower()
            if act in ("on", "off"):
                ctrl.set_power(act == "on")
            elif act == "toggle":
                ctrl.set_power(not ctrl.status().get("power", False))
            else:
                return jsonify({"ok": False, "error": f"未知 action: {act}"}), 400
        elif "brightness" in payload:
            ctrl.set_brightness(payload["brightness"])
        elif "color_temp" in payload:
            ctrl.set_color_temp(payload["color_temp"])
        elif "property" in payload:
            # 通用属性写入：{"property":"cook_mode","value":2}
            ctrl.set_property(payload["property"], payload["value"])
        else:
            return jsonify({"ok": False, "error": "缺少控制参数"}), 400
        return jsonify({"ok": True, "state": ctrl.status()})
    except KeyError as exc:
        return jsonify({"ok": False, "error": f"缺少参数: {exc}"}), 400
    except Exception as exc:
        log.exception("控制设备 %s 失败", device_id)
        return jsonify({"ok": False, "error": friendly_error(exc)}), 500
    finally:
        if ctrl is not None:
            try:
                ctrl.close()
            except Exception:
                pass


@app.route("/devices/<device_id>/action", methods=["POST"])
def bridge_action(device_id: str):
    """调用动作型设备的动作，如电饭煲的开始/取消烹饪。

    请求体：{"action":"start_cook","params":[{"piid":5,"value":2}]}
    params 可省略，省略时用配置里的默认入参。
    """
    cfg = find_by_id(device_id)
    if cfg is None:
        return jsonify({"ok": False, "error": "找不到该设备"}), 404

    payload = request.get_json(silent=True) or {}
    name = payload.get("action")
    if not name:
        return jsonify({"ok": False, "error": "缺少 action 名称"}), 400

    ctrl = None
    try:
        ctrl = build_controller(cfg)
        ctrl.call_action(name, payload.get("params"))
        return jsonify({"ok": True, "action": name, "state": ctrl.status()})
    except NotImplementedError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        log.exception("调用设备 %s 动作 %s 失败", device_id, name)
        return jsonify({"ok": False, "error": friendly_error(exc)}), 500
    finally:
        if ctrl is not None:
            try:
                ctrl.close()
            except Exception:
                pass


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "unable to discover" in low or "no response" in low:
        return "设备无响应：确认设备在线、IP 正确、与本机同网段"
    if "timeout" in low or "timed out" in low:
        return "连接超时：检查设备是否在线、IP 是否正确"
    if "token" in low or "checksum" in low or "decrypt" in low:
        return "token 错误或已变更：重新用提取工具导出 token"
    if "no route" in low or "unreachable" in low or "network" in low:
        return "网络不可达：确认设备与本机在同一网段"
    return msg or exc.__class__.__name__


def ensure_devices_file() -> None:
    """首次启动生成一个空的 devices.json，避免用假数据污染配置。"""
    if DEVICES_FILE.exists():
        return
    log.info("未找到 devices.json，已生成空配置，请填入设备后刷新页面")
    DEVICES_FILE.write_text(
        json.dumps({"devices": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    log.info("paperbutler Copyright (C) 2026 The paperbutler Authors | GPL-3.0-only | NO WARRANTY; see LICENSE")
    ensure_devices_file()
    # 监听 0.0.0.0 才能让局域网里的设备访问；用 HTTP（设备端自签证书一律失败）
    app.run(host="0.0.0.0", port=9090, debug=False)
