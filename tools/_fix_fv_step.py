"""把 CI 里那段坏掉的 sed 换成 python 调用。"""

import io

W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
lines = io.open(W, encoding="utf-8").read().split("\n")

# 找到 "把 XNU payload 作为 RAW section 塞进 FV" 那段，整块替换
start = None
for i, l in enumerate(lines):
    if "把 XNU payload 作为 RAW section 塞进 FV" in l:
        start = i
        break
if start is None:
    raise SystemExit("找不到 FV 注入段")

# 往回到 echo 之前的缩进行开始，往后到 "echo \"没有 payload-blob.img" 那段的结尾 fi
end = start
while end < len(lines) and "没有 payload-blob.img" not in lines[end]:
    end += 1
while end < len(lines) and lines[end].strip() != "fi":
    end += 1

new_block = r'''          echo "=== 把 XNU payload 作为 RAW section 塞进 FV ==="
          if [ -f rom/xnu/payload-blob.img ]; then
            cp rom/xnu/payload-blob.img edk2-msm/Platform/Xiaomi/sm8550/probe/xnu_payload.bin
            ls -l edk2-msm/Platform/Xiaomi/sm8550/probe/xnu_payload.bin
            python3 tools/add_fv_payload.py \
              edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf \
              Platform/Xiaomi/sm8550/probe/xnu_payload.bin
            echo "--- 确认 FDF ---"
            grep -n -A3 "XNU PAYLOAD" edk2-msm/Platform/Qualcomm/sm8550/sm8550.fdf || true
          else
            echo "没有 payload-blob.img，跳过 FV 注入"
          fi'''

lines[start:end + 1] = new_block.split("\n")
io.open(W, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print(f"已替换 FV 注入段（L{start+1}..L{end+1}）")

t = "\n".join(lines)
bad = [i for i, l in enumerate(lines, 1) if not l.strip().startswith("#") and l.count('"') % 2]
print("引号不配对:", bad[:5] if bad else "无")

# 本地测一下 add_fv_payload
import subprocess
p = subprocess.run(["python", r"E:\ios-on-fuxi\tools\add_fv_payload.py"], capture_output=True, text=True)
print("脚本自检:", p.stdout.strip() or p.stderr.strip())
