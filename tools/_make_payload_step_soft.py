import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

# ---------- 1) payload 步骤改成"尽力而为"，并把日志留下来 ----------
start = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "取最新 XNU 内核" in l:
        start = i
        break
if start is None:
    raise SystemExit("找不到 payload 步骤")

end = start + 1
while end < len(lines) and not lines[end].strip().startswith("- "):
    end += 1

NEW = r'''      - name: 取最新 XNU 内核并生成 payload（嵌入固件，失败不影响固件构建）
        run: |
          # 这一步是"尽力而为"：拿不到内核就跳过，固件照常编（只是不带 XNU）
          set +e
          exec > >(tee -a xnu-payload.log) 2>&1
          set -x
          mkdir -p rom/xnu

          echo "=== 找最新的 xnu-kernel 产物 ==="
          API="https://api.github.com/repos/${{ github.repository }}/actions/artifacts?per_page=100"
          curl -s -H "Authorization: Bearer ${{ github.token }}" "$API" -o /tmp/arts.json
          head -c 300 /tmp/arts.json; echo
          ART=$(python3 -c "
          import json
          d = json.load(open('/tmp/arts.json'))
          a = [x for x in d.get('artifacts', []) if x['name'] == 'xnu-kernel' and not x['expired']]
          a.sort(key=lambda x: x['created_at'])
          print(a[-1]['archive_download_url'] if a else '')
          ")
          echo "artifact url: [$ART]"
          if [ -z "$ART" ]; then echo "没有 xnu-kernel 产物，跳过 XNU 嵌入"; cp xnu-payload.log ../xnu-payload.log; exit 0; fi

          curl -sL -H "Authorization: Bearer ${{ github.token }}" "$ART" -o /tmp/k.zip
          ls -l /tmp/k.zip
          rm -rf /tmp/k; mkdir -p /tmp/k
          unzip -oq /tmp/k.zip -d /tmp/k || echo "解压失败"
          KERNEL=$(find /tmp/k -type f -name "kernel.*" | head -1)
          echo "kernel: [$KERNEL]"
          if [ -z "$KERNEL" ]; then echo "产物里没有内核文件"; cp xnu-payload.log ../xnu-payload.log; exit 0; fi

          echo "=== 生成 Apple 设备树 ==="
          python3 tools/mkadt_fuxi.py rom/xnu/fuxi.adt || echo "mkadt 失败"
          ls -l rom/xnu/fuxi.adt

          echo "=== 生成 payload ==="
          python3 tools/mkpayload_fuxi.py "$KERNEL" rom/xnu/fuxi.adt rom/xnu/payload.bin \
            --cmdline "debug=0xc serial=3 cpus=1 keepsyms=1 -v" || echo "mkpayload 失败"
          ls -l rom/xnu/payload.bin

          if [ -f rom/xnu/payload.bin ]; then
            echo "=== 生成 .incbin 汇编 ==="
            {
              echo '.section .rodata'
              echo '.global gXnuPayload'
              echo '.global gXnuPayloadEnd'
              echo '.align 12'
              echo 'gXnuPayload:'
              echo ".incbin \"$PWD/rom/xnu/payload.bin\""
              echo 'gXnuPayloadEnd:'
            } > loader/xnu_payload.S
            cat loader/xnu_payload.S
          else
            echo "没有 payload.bin，保持占位 .S（固件里不带 XNU）"
          fi

          cp xnu-payload.log ../xnu-payload.log
          exit 0

'''

lines[start:end] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"payload 步骤已替换（L{start+1}..L{end}）")

# ---------- 2) 上传里加 xnu-payload.log ----------
text = io.open(W, encoding="utf-8").read()
if "            xnu-payload.log" not in text:
    text = text.replace("            build.log\n", "            build.log\n            xnu-payload.log\n")
    io.open(W, "w", encoding="utf-8", newline="\n").write(text)
    print("已把 xnu-payload.log 加入产物")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
