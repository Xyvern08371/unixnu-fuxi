"""给 XnuLoad 加诊断：把枚举到的每个块设备的大小打到屏幕上。"""

import io

P = r"E:\ios-on-fuxi\loader\XnuLoad.c"
t = io.open(P, encoding="utf-8").read()

# 1) 函数签名加日志回调
t = t.replace(
    """EFI_STATUS
XnuLoadFromBlock (
  OUT VOID   **Buf,
  OUT UINTN  *Size
  )""",
    """typedef VOID (*XNU_LOG_FN)(CONST CHAR8 *Tag, UINT64 Value);

EFI_STATUS
XnuLoadFromBlock (
  OUT VOID       **Buf,
  OUT UINTN      *Size,
  IN  XNU_LOG_FN  Log
  )""",
    1,
)

# 2) 枚举后打印设备数量
t = t.replace(
    """  if (EFI_ERROR (Status)) {
    return Status;
  }
""",
    """  if (EFI_ERROR (Status)) {
    return Status;
  }

  if (Log != NULL) {
    Log ("BLK HANDLES", (UINT64)Count);
  }
""",
    1,
)

# 3) 每台设备打印大小（最多 6 台）
t = t.replace(
    """    BlkSize   = Bio->Media->BlockSize;
    MediaSize = (UINTN)((Bio->Media->LastBlock + 1) * BlkSize);""",
    """    BlkSize   = Bio->Media->BlockSize;
    MediaSize = (UINTN)((Bio->Media->LastBlock + 1) * BlkSize);

    if ((Log != NULL) && (I < 6)) {
      Log ("BLK SIZE", (UINT64)MediaSize);
    }
""",
    1,
)

# 4) 分配改用 AllocatePages（15.8MB 用 pool 容易失败）
t = t.replace(
    """#include <Protocol/BlockIo.h>""",
    """#include <Protocol/BlockIo.h>""",
)
t = t.replace(
    """    Data = AllocatePool ((UINTN)Len);
    if (Data == NULL) {
      continue;
    }""",
    """    {
      EFI_PHYSICAL_ADDRESS  Pages;

      Pages = 0;
      Status = gBS->AllocatePages (
                      AllocateAnyPages,
                      EfiLoaderData,
                      (UINTN)((Len + EFI_PAGE_SIZE - 1) / EFI_PAGE_SIZE),
                      &Pages
                      );
      if (EFI_ERROR (Status)) {
        if (Log != NULL) {
          Log ("ALLOC FAIL", (UINT64)Len);
        }
        continue;
      }
      Data = (UINT8 *)(UINTN)Pages;
    }""",
    1,
)

# 5) 找到时打印一句
t = t.replace(
    """    if (Off == (UINTN)Len) {
      *Buf  = Data;
      *Size = (UINTN)Len;""",
    """    if (Off == (UINTN)Len) {
      if (Log != NULL) {
        Log ("BLK FOUND", (UINT64)Len);
      }
      *Buf  = Data;
      *Size = (UINTN)Len;""",
    1,
)

# 6) 没找到也打印
t = t.replace(
    """  if (Handles != NULL) {
    FreePool (Handles);
  }
  return EFI_NOT_FOUND;""",
    """  if (Handles != NULL) {
    FreePool (Handles);
  }
  if (Log != NULL) {
    Log ("BLK NOTFOUND", 0);
  }
  return EFI_NOT_FOUND;""",
    1,
)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("XnuLoad.c 已加诊断")

# ---------- Probe.c：传日志回调 ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()
c = c.replace(
    "extern EFI_STATUS   XnuLoadFromBlock (VOID **Buf, UINTN *Size);",
    "extern EFI_STATUS   XnuLoadFromBlock (VOID **Buf, UINTN *Size,\n"
    "                                      VOID (*Log)(CONST CHAR8 *, UINT64));",
    1,
)
c = c.replace(
    """      if (!EFI_ERROR (XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize))) {
        if (mXnuBufSize > 0) {
          Fill (0xFF001800);
          mLogY = 40;
          XnuScreenLog ("BLOCK PAYLOAD", mXnuBufSize);
          XnuScreenLog ("EMBEDDED", XnuPayloadSize ());
        }
      }""",
    """      Fill (0xFF001800);
      mLogY = 40;
      XnuScreenLog ("EMBEDDED", XnuPayloadSize ());
      XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      XnuScreenLog ("BUF SIZE", mXnuBufSize);""",
    1,
)
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已传日志回调")
print("大括号:", c.count("{"), "vs", c.count("}"))
