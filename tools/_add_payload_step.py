import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

# 在 "注入探针驱动" 之前插入 XNU payload 步骤
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "注入探针驱动" in l:
        anchor = i
        break
if anchor is None:
    raise SystemExit("找不到锚点")

NEW = r'''      - name: 取最新 XNU 内核并生成 payload（嵌入固件）
        run: |
          set -euo pipefail
          mkdir -p rom/xnu

          echo "=== 找最新的 xnu-kernel 产物 ==="
          ART=$(curl -s -H "Authorization: Bearer ${{ github.token }}" \
            "https://api.github.com/repos/${{ github.repository }}/actions/artifacts?per_page=100" \
            | python3 -c "import sys,json;d=json.load(sys.stdin);a=[x for x in d['artifacts'] if x['name']=='xnu-kernel' and not x['expired']];a.sort(key=lambda x:x['created_at']);print(a[-1]['archive_download_url'] if a else '')")
          if [ -z "$ART" ]; then echo "没有 xnu-kernel 产物，跳过 XNU 嵌入"; exit 0; fi
          curl -sL -H "Authorization: Bearer ${{ github.token }}" "$ART" -o /tmp/k.zip
          rm -rf /tmp/k && mkdir -p /tmp/k && unzip -oq /tmp/k.zip -d /tmp/k
          KERNEL=$(find /tmp/k -name "kernel.*.fuxi" -type f | head -1)
          echo "内核: $KERNEL"
          ls -l "$KERNEL"

          echo "=== 生成 Apple 设备树 ==="
          python3 tools/mkadt_fuxi.py rom/xnu/fuxi.adt
          ls -l rom/xnu/fuxi.adt

          echo "=== 生成 payload ==="
          python3 tools/mkpayload_fuxi.py "$KERNEL" rom/xnu/fuxi.adt rom/xnu/payload.bin \
            --cmdline "debug=0xc serial=3 cpus=1 keepsyms=1 -v"
          ls -l rom/xnu/payload.bin

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

'''

lines[anchor:anchor] = NEW.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已在行 {anchor+1} 前插入 payload 步骤")

# 自检
lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1)
       if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
