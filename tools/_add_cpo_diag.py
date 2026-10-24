import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

# 在第 1 步成功后加入 cpo.json 诊断
old = '''          cp step1.log "$GITHUB_WORKSPACE/step1.log"
          echo "第 1 步成功"
          ls build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/ | head -20
          find build/xnu/ios-obj -name "*.cpo.json" | head -5'''
new = '''          cp step1.log "$GITHUB_WORKSPACE/step1.log"
          echo "第 1 步成功"

          echo "===== ios-obj 顶层 ====="
          ls -la build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/ 2>/dev/null | head -30 || echo "(目录不存在)"

          echo "===== iokit/DEVELOPMENT 目录 ====="
          ls -la build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/ 2>/dev/null | head -40 || echo "(目录不存在)"

          echo "===== 所有 .json 记录 ====="
          find build/xnu/ios-obj -name "*.json" 2>/dev/null | head -20 || echo "(没有 .json)"
          echo "json 总数: $(find build/xnu/ios-obj -name '*.json' 2>/dev/null | wc -l)"

          echo "===== 所有 .o / .cpo ====="
          echo "o 总数:   $(find build/xnu/ios-obj -name '*.o' 2>/dev/null | wc -l)"
          echo "cpo 总数: $(find build/xnu/ios-obj -name '*.cpo' 2>/dev/null | wc -l)"

          echo "===== 目标文件 ====="
          find build/xnu -name "mach.development.bcm2837*" 2>/dev/null | head -5 || echo "(没有内核产物)"

          echo "===== step1.log 中的 -MJ 行 ====="
          grep -o '\\-MJ [^ ]*' step1.log 2>/dev/null | head -5 || echo "(日志里没有 -MJ)"'''

if old in t:
    t = t.replace(old, new, 1)
    print("第 1 步诊断: ok")
else:
    print("锚点没找到")

io.open(p, "w", encoding="utf-8", newline="\n").write(t)

import yaml
yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效")
