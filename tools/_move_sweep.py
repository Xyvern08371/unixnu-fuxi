import io
import re

P = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(P, encoding="utf-8").read()

# 1) 摘掉现在的位置（在 DrawString 原型之后、注释之前）
start_marker = "/** 帧缓冲是 cacheable 的：少量分散写留在缓存里屏幕看不到，按缓存行回扫推上去 */"
i = c.find(start_marker)
if i < 0:
    raise SystemExit("找不到 SweepFb 块")

# 从 start_marker 到其后的第一个 "\n}\n\n"
j = c.find("\n}\n", i)
assert j > 0
block = c[i:j + 3]
c = c[:i] + c[j + 3:]
print("已移除旧 SweepFb 块，长度", len(block))

# 2) 插到全局变量之后
anchor = "STATIC UINTN       mXnuBufSize;"
assert anchor in c, "找不到全局变量锚点"
newfn = """

/** 帧缓冲是 cacheable 的：少量分散写留在缓存里屏幕看不到，按缓存行回扫推上去 */
STATIC
VOID
SweepFb (
  VOID
  )
{
  volatile UINT32  *Pix;
  UINTN             Count;
  UINTN             k;

  if (mFb == NULL || mFbSize < 4) {
    return;
  }
  Pix   = (volatile UINT32 *)mFb;
  Count = mFbSize / 4;
  for (k = 0; k < Count; k += 16) {
    Pix[k] = Pix[k];
  }
}
"""
c = c.replace(anchor, anchor + newfn, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(c)

# 3) 校验顺序
lines = c.split("\n")
pos = {}
for i, l in enumerate(lines, 1):
    if "STATIC UINT8      *mFb;" in l:
        pos["mFb 声明"] = i
    if l.strip().startswith("SweepFb (") and pos.get("SweepFb 定义") is None:
        pos["SweepFb 定义"] = i
    if l.strip().startswith("XnuScreenLog (") and pos.get("XnuScreenLog") is None:
        pos["XnuScreenLog"] = i
    if "SweepFb ();" in l and pos.get("SweepFb 调用") is None:
        pos["SweepFb 调用"] = i

print("位置:", pos)
ok = pos.get("mFb 声明", 0) < pos.get("SweepFb 定义", 0) < pos.get("SweepFb 调用", 0)
print("顺序正确:", ok)
print("大括号:", c.count("{"), "vs", c.count("}"))
