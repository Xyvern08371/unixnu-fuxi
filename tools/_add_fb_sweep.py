"""给 Probe.c 的绘制加缓存回扫，否则少量像素留在 cache 里不上屏。"""

import io

P = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(P, encoding="utf-8").read()

# 1) 加 SweepFb 函数（放在 PutPixel 之前）
if "SweepFb" not in c:
    sweep = '''/**
  帧缓冲是 cacheable 的：少量分散写会留在缓存里，屏幕上看不到。
  这里按缓存行回扫（读改写），把脏行推到显存。
**/
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

'''
    c = c.replace("STATIC\nVOID\nPutPixel (", sweep + "STATIC\nVOID\nPutPixel (", 1)

# 2) Fill 结尾回扫
c = c.replace(
    """  Pix   = (volatile UINT32 *) mFb;
  Count = mFbSize / 4;
  for (i = 0; i < Count; i++) {
    Pix[i] = Color;
  }
}""",
    """  Pix   = (volatile UINT32 *) mFb;
  Count = mFbSize / 4;
  for (i = 0; i < Count; i++) {
    Pix[i] = Color;
  }
  SweepFb ();
}""",
    1,
)

# 3) XnuScreenLog 画完回扫
c = c.replace(
    """  DrawString (20, mLogY, Line, 0xFFFFFFFF);
  mLogY += 24;""",
    """  DrawString (20, mLogY, Line, 0xFFFFFFFF);
  SweepFb ();
  mLogY += 24;""",
    1,
)

io.open(P, "w", encoding="utf-8", newline="\n").write(c)
print("已加缓存回扫")
print("SweepFb 出现:", c.count("SweepFb"))
print("大括号:", c.count("{"), "vs", c.count("}"))

# 检查 SweepFb 是否在 Fill 之前定义（Fill 在 351 行左右，PutPixel 333）
lines = c.split("\n")
for i, l in enumerate(lines, 1):
    if "SweepFb" in l and l.strip().startswith("SweepFb ("):
        print("SweepFb 定义在第", i, "行")
