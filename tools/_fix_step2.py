import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

old = """      - name: 第 2 步 - 编设备 archive
        run: |
          set -uo pipefail
          cd UniXNU
          COMPS=(ArmDTPlatform ArmCpu NativeUfs NativeAES NativeVirtioBlock \\
                 NativeRamBlock NativeVirtioConsole NativeLegacyDisplay \\
                 NativeMobileDisplay NativeAdreno)
          ok=""; bad=""
          for c in "${COMPS[@]}"; do
            echo "===== build-arm-driver.py $c ====="
            if python3 scripts/build-arm-driver.py "$c" > "step2-$c.log" 2>&1; then
              echo "OK   $c"; ok="$ok $c"
            else
              echo "FAIL $c"; tail -25 "step2-$c.log" || true; bad="$bad $c"
            fi
            cp "step2-$c.log" "$GITHUB_WORKSPACE/" 2>/dev/null || true
          done
          echo "---- 汇总 ----"
          echo "成功:$ok"
          echo "失败:${bad:- 无}"
          echo "---- build/ 下的 .a ----"
          find build -name "*.a" | head -40
          [ -n "$ok" ] || { echo "一个 archive 都没编出来"; exit 1; }"""

new = """      - name: 第 2 步 - 编设备 archive
        run: |
          set -uo pipefail
          cd UniXNU
          COMPS=(ArmDTPlatform ArmCpu NativeUfs NativeAES NativeVirtioBlock \\
                 NativeRamBlock NativeVirtioConsole NativeLegacyDisplay \\
                 NativeMobileDisplay NativeAdreno)
          ok=""; bad=""

          # 先把 cpo.json 的位置和内容摸清楚，失败时这就是唯一线索
          echo "===== cpo.json 位置 ====="
          find build -name "IOPlatformExpert.cpo.json" 2>/dev/null | head -5 || true
          echo "===== ios-obj 下的 json 总数 ====="
          find build/xnu/ios-obj -name "*.json" 2>/dev/null | wc -l || true
          echo "===== build/xnu/ios-obj 顶层 ====="
          ls build/xnu/ios-obj 2>/dev/null || echo "(缺 build/xnu/ios-obj)"
          echo "===== iokit 目录 ====="
          ls build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit 2>/dev/null || echo "(缺 iokit)"
          ls build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT 2>/dev/null || echo "(缺 iokit/DEVELOPMENT)"

          for c in "${COMPS[@]}"; do
            echo "::group::build-arm-driver.py $c"
            if python3 scripts/build-arm-driver.py "$c" > "step2-$c.log" 2>&1; then
              echo "OK   $c"; ok="$ok $c"
            else
              echo "FAIL $c"
              echo "----- step2-$c.log 全部输出 -----"
              cat "step2-$c.log" || true
              bad="$bad $c"
            fi
            echo "::endgroup::"
            cp "step2-$c.log" "$GITHUB_WORKSPACE/" 2>/dev/null || true
          done
          echo "---- 汇总 ----"
          echo "成功:$ok"
          echo "失败:${bad:- 无}"
          echo "---- build/ 下的 .a ----"
          find build -name "*.a" | head -40 || true

          # 把失败详情写进 step summary，这样从 API 的 jobs 响应就能读到
          {
            echo "## step2 结果"
            echo "- 成功: \\`$ok\\`"
            echo "- 失败: \\`${bad:-无}\\`"
            for c in $bad; do
              echo ""
              echo "### $c 失败日志（最后 60 行）"
              echo '```'
              tail -60 "step2-$c.log" 2>/dev/null || echo "(无日志)"
              echo '```'
            done
          } >> "$GITHUB_STEP_SUMMARY"

          [ -n "$ok" ] || { echo "一个 archive 都没编出来"; exit 1; }"""

if old in t:
    t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("第 2 步已改：加诊断 + step summary")
else:
    print("锚点没找到")
    i = t.find("第 2 步 - 编设备 archive")
    print(repr(t[i-5:i+300]))

import yaml
d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效，steps:")
for s in d["jobs"]["build"]["steps"]:
    print("  -", s.get("name", s.get("uses", "?")))
