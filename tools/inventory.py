#!/usr/bin/env python3
"""inventory.py -- 从合并后的设备树生成"引导必需设备清单"

输入 fuxi_merged.dtb, 输出一份按优先级排序的硬件清单:
  P1 没有它连第一行日志都打不出来
  P2 早期启动必需(存储/PMIC/时钟)
  P3 能看到东西/能交互
  P4 以后再说

用法:
  python inventory.py fuxi_merged.dtb -o ../docs/hardware-inventory.md
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "appledt"))

import apple_dt as A
import overlay as O

# (优先级, 类别, 匹配的 compatible 关键字)
RULES = [
    (1, "调试串口",     ["geni-debug-uart"]),
    (1, "中断控制器",   ["arm,gic-v3", "qcom,pdc"]),
    (1, "系统定时器",   ["arm,armv8-timer"]),
    (1, "PSCI 电源管理", ["arm,psci"]),
    (1, "CPU 拓扑",     ["arm,cortex", "arm,armv8"]),
    (2, "UFS 存储",     ["qcom,ufshc", "ufs"]),
    (2, "PMIC / SPMI",  ["spmi-pmic-arb", "pm8550", "pmk8550", "pmr735"]),
    (2, "时钟控制",     ["gcc", "rpmh-clk", "camcc", "dispcc", "gpucc"]),
    (2, "引脚控制",     ["pinctrl"]),
    (2, "RPMh / 通信",  ["rpmh", "ipcc", "smem", "smp2p"]),
    (3, "显示 MDP",     ["sde-kms", "mdss"]),
    (3, "DSI / 面板",   ["dsi", "panel"]),
    (3, "USB",          ["dwc3", "usb"]),
    (3, "触摸",         ["xiaomi-touch", "touchscreen", "goodix", "focaltech"]),
    (3, "I2C / SPI",    ["geni-i2c", "geni-spi", "i2c"]),
    (4, "GPU",          ["adreno", "kgsl"]),
    (4, "音频",         ["wcd", "lpass", "macro", "sound"]),
    (4, "Wi-Fi / 蓝牙", ["wcn", "wlan", "bluetooth"]),
    (4, "摄像头",       ["cam", "cci", "eeprom", "actuator"]),
    (4, "NPU / 其它",   ["npu", "adsp", "cdsp"]),
]

P_TITLE = {
    1: "P1 — 没有它连第一行日志都打不出来",
    2: "P2 — 早期启动必需",
    3: "P3 — 能看见、能交互",
    4: "P4 — 以后再说",
}


def reg_of(node: A.Node, parent: A.Node) -> str:
    raw = node.props.get("reg")
    if not raw or len(raw) < 4:
        return "-"
    ac = parent.get_u32("#address-cells", 2) or 2
    sc = parent.get_u32("#size-cells", 2) or 2
    cells = []
    off = 0
    while off + 4 <= len(raw) and len(cells) < 4:
        cells.append(struct.unpack(">I", raw[off:off + 4])[0])
        off += 4
    if ac == 2 and len(cells) >= 2:
        addr = (cells[0] << 32) | cells[1]
        size = ((cells[2] << 32) | cells[3]) if len(cells) >= 4 else 0
        return "0x%x + 0x%x" % (addr, size)
    return "0x%x" % cells[0]


NOISE = ("-debug", "spmi-debug", "glink", "_log", "rpmh-regulator", "regulator-",
         "thermal-zones", "iommu_test_device", "reserved-memory")

MAX_ROWS = 10          # 每个优先级最多列这么多行, 其余折叠


def is_noise(path: str) -> bool:
    low = path.lower()
    return any(k in low for k in NOISE)


def classify(node: A.Node) -> tuple[int, str] | None:
    comp = node.get_str("compatible", "") or ""
    name = node.name.lower()
    hay = comp.lower() + " " + name
    best = None
    for prio, cat, keys in RULES:
        for k in keys:
            if k in hay:
                if best is None or prio < best[0]:
                    best = (prio, cat)
    return best


def collect(tree: A.Node) -> list[dict]:
    items = []
    for node, path in O.walk_path(tree):
        if node is tree:
            continue
        hit = classify(node)
        if hit is None or is_noise(path):
            continue
        prio, cat = hit
        parent = tree
        if path.count("/") > 1:
            try:
                parent = tree.find(path.rsplit("/", 1)[0])
            except A.DtError:
                parent = tree
        items.append({
            "prio": prio,
            "cat": cat,
            "path": path,
            "compat": (node.get_str("compatible", "") or "-").split("\0")[0][:52],
            "reg": reg_of(node, parent),
            "status": node.get_str("status", "okay"),
            "irqs": "yes" if "interrupts" in node.props else "-",
        })
    # 同一路径只保留优先级最高的一条
    dedup: dict[str, dict] = {}
    for it in items:
        key = it["path"]
        if key not in dedup or it["prio"] < dedup[key]["prio"]:
            dedup[key] = it
    return sorted(dedup.values(), key=lambda x: (x["prio"], x["cat"], x["path"]))


def specials(tree: A.Node) -> list[tuple[str, str]]:
    out = []
    psci_node, psci_path = None, None
    for node, path in O.walk_path(tree):
        if "arm,psci" in (node.get_str("compatible") or ""):
            psci_node, psci_path = node, path
            break
    if psci_node is None:
        out.append(("PSCI", "缺失"))
    else:
        out.append(("PSCI", "%s, method=%s" % (psci_path, psci_node.get_str("method", "-"))))
    ch = tree.try_find("/chosen")
    out.append(("stdout-path", (ch.get_str("stdout-path", "-") if ch else "-")))
    out.append(("bootargs", (ch.get_str("bootargs", "-") if ch else "-")[:70]))

    timer = None
    for node, path in O.walk_path(tree):
        if "arm,armv8-timer" in (node.get_str("compatible") or ""):
            timer = path
            break
    out.append(("定时器节点", timer or "缺失"))

    rm = tree.try_find("/reserved-memory")
    out.append(("保留内存区", "%d 项" % len(rm.children) if rm else "缺失"))
    return out


def render(tree: A.Node, src: str) -> str:
    items = collect(tree)
    lines = ["# fuxi 引导必需设备清单", "",
             "由 `tools/inventory.py` 从 `%s` 自动生成，**不要手改**。" % src,
             "数据来源：PixelOS_fuxi-17.0-20260929 的 vendor_boot + dtbo（已合并）。", "",
             "## 关键参数", "", "| 项 | 值 |", "|---|---|"]
    for k, v in specials(tree):
        lines.append("| %s | `%s` |" % (k, v))

    lines.append("")
    for prio in sorted({i["prio"] for i in items}):
        group = [i for i in items if i["prio"] == prio]
        lines.append("## %s" % P_TITLE[prio])
        lines.append("")
        lines.append("| 类别 | 节点 | compatible | reg | 中断 | status |")
        lines.append("|---|---|---|---|---|---|")
        for i in group[:MAX_ROWS]:
            lines.append("| %s | `%s` | `%s` | `%s` | %s | %s |" % (
                i["cat"], i["path"], i["compat"], i["reg"], i["irqs"], i["status"]))
        if len(group) > MAX_ROWS:
            rest = group[MAX_ROWS:]
            lines.append("| … | 另有 %d 项（%s） | | | | |" % (
                len(rest), "、".join(sorted({r["cat"] for r in rest}))))
        lines.append("")

    total = len(items)
    disabled = [i for i in items if i["status"] not in ("okay", "ok")]
    lines.append("## 统计")
    lines.append("")
    lines.append("- 归类到清单的节点：**%d**" % total)
    lines.append("- 其中 status != okay（需要先打开）：**%d**" % len(disabled))
    if disabled:
        lines.append("")
        for i in disabled[:15]:
            lines.append("  - `%s` (%s)" % (i["path"], i["status"]))
    lines.append("")
    lines.append("> 用法：P1 全部打通之前，不要碰 P3 以后的东西。")
    lines.append("> 每打通一项，就把它的状态从 ⬜ 改成 ✅（建议单独维护一张进度表）。")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="inventory", description="设备树 -> 引导必需清单")
    ap.add_argument("dtb")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)

    try:
        with open(args.dtb, "rb") as fh:
            tree = A.parse(fh.read())
    except (A.DtError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    text = render(tree, os.path.basename(args.dtb))
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("写出 %s (%d 字节)" % (args.out, len(text.encode("utf-8"))))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
