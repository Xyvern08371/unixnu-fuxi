import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
t = io.open(W, encoding="utf-8").read()
lines = t.split("\n")

# 在 "注入探针驱动" 步骤里追加：把 UFS / 分区 / FAT 驱动加进 FDF
anchor = None
for i, l in enumerate(lines):
    if l.strip().startswith("- name:") and "注入探针驱动" in l:
        anchor = i
        break
if anchor is None:
    raise SystemExit("找不到注入步骤")

end = anchor + 1
while end < len(lines) and not lines[end].strip().startswith("- "):
    end += 1

extra = r'''
          echo "=== 查找可用的块设备驱动 ==="
          UFS=$(find edk2-msm -iname "Ufs*Dxe*.inf" -o -iname "*UfsDxe*.inf" 2>/dev/null | head -1)
          PART=$(find edk2-msm -iname "PartitionDxe.inf" 2>/dev/null | head -1)
          FAT=$(find edk2-msm -iname "Fat.inf" -o -iname "FatDxe.inf" 2>/dev/null | head -1)
          echo "UFS   = [$UFS]"
          echo "PART  = [$PART]"
          echo "FAT   = [$FAT]"
          echo "=== 已在 FDF 里的相关驱动 ==="
          grep -inE "ufs|partition|fat" edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf | head -20 || true

          FDF=edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf
          for INF in "$UFS" "$PART" "$FAT"; do
            if [ -n "$INF" ]; then
              REL=$(echo "$INF" | sed "s|^edk2-msm/||")
              if ! grep -q "$REL" "$FDF"; then
                sed -i "/INF MdeModulePkg\/Universal\/BdsDxe\/BdsDxe.inf/a\\  INF $REL" "$FDF"
                echo "已加入 FDF: $REL"
              else
                echo "FDF 里已有: $REL"
              fi
            fi
          done
          echo "=== 确认 ==="
          grep -inE "ufs|partition|fat" "$FDF" | head -20 || true
'''

lines[end:end] = extra.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("已加块设备驱动注入")

lines2 = io.open(W, encoding="utf-8").read().split("\n")
bad = [i for i, l in enumerate(lines2, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")
