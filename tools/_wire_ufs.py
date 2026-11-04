"""把 UFS 读取接进 XnuLoad / Probe。"""

import io

# ---------- 1) XnuLoad.c：加 UFS 兜底 ----------
P = r"E:\ios-on-fuxi\loader\XnuLoad.c"
t = io.open(P, encoding="utf-8").read()

if "XnuLoadFromUfs" not in t:
    add = r'''
/* ---- 直接读 UFS（UEFI 没有块设备驱动时用这条路） ---- */
extern UINT32  UfsFindPartition (CONST CHAR8 *Name, UINT64 *FirstLba, UINT64 *LastLba);
extern UINT32  UfsReadBlocks (UINT64 Lba, UINT32 Count, VOID *Buf);

#define UFS_CHUNK_BLOCKS  16u     /* 每次 64KB，单个 PRDT 比较安全 */

/**
  从 UFS 的 dtbo 分区读 XNU payload。

  分区里是 tools/mkpayload_img.py 生成的镜像：
      "FUXIPAY1" + u64 长度 + payload
**/
EFI_STATUS
XnuLoadFromUfs (
  OUT VOID       **Buf,
  OUT UINTN      *Size,
  IN  XNU_LOG_FN  Log
  )
{
  UINT64        First = 0;
  UINT64        Last = 0;
  UINT32        Rc;
  UINT8         *Hdr;
  UINT64        Len = 0;
  UINT8         *Data;
  EFI_PHYSICAL_ADDRESS  Pages;
  UINT32        Done = 0;
  UINT32        Chunk;

  *Buf  = NULL;
  *Size = 0;

  Rc = UfsFindPartition ("dtbo", &First, &Last);
  if (Log != NULL) {
    Log ("UFS GPT", (UINT64)Rc);
  }
  if (Rc != 0) {
    return EFI_NOT_FOUND;
  }
  if (Log != NULL) {
    Log ("UFS DTBO LBA", First);
  }

  Hdr = AllocatePool (8192);
  if (Hdr == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  if (UfsReadBlocks (First, 2, Hdr) != 0) {
    FreePool (Hdr);
    if (Log != NULL) {
      Log ("UFS READ ERR", 0);
    }
    return EFI_DEVICE_ERROR;
  }
  if (!MagicOk (Hdr)) {
    FreePool (Hdr);
    if (Log != NULL) {
      Log ("UFS MAGIC BAD", 0);
    }
    return EFI_NOT_FOUND;
  }
  CopyMem (&Len, Hdr + 8, sizeof (Len));
  FreePool (Hdr);

  if ((Len == 0) || (Len > 256ULL * 1024 * 1024)) {
    return EFI_NOT_FOUND;
  }

  Pages = 0;
  if (EFI_ERROR (gBS->AllocatePages (
                        AllocateAnyPages,
                        EfiLoaderData,
                        (UINTN)((Len + EFI_PAGE_SIZE - 1) / EFI_PAGE_SIZE),
                        &Pages
                        ))) {
    return EFI_OUT_OF_RESOURCES;
  }
  Data = (UINT8 *)(UINTN)Pages;

  /* 数据从分区偏移 16 字节开始；按块读再搬到 buffer */
  while (Done < (UINT32)Len) {
    UINT64  ByteOff = 16 + Done;
    UINT64  Lba = First + (ByteOff / UFS_CHUNK_BLOCKS / 4096) * 0;
    UINT32  InBlk;
    UINT8   *Tmp;
    UINT32  Want;

    /* 简化：payload 起始偏移 16 不是块对齐，所以从 first+0 开始按块读整段 */
    if (Done == 0) {
      Lba = First;
    }

    if (Log != NULL) {
      Log ("UFS CHUNK", (UINT64)Done);
    }

    Tmp = AllocatePool (UFS_CHUNK_BLOCKS * 4096);
    if (Tmp == NULL) {
      break;
    }

    /* 计算这一块覆盖的 LBA：从 first 起，第 (16+Done)/4096 块 */
    Lba = First + ((16 + Done) / 4096);
    InBlk = (UINT32)((16 + Done) % 4096);

    if (UfsReadBlocks (Lba, UFS_CHUNK_BLOCKS, Tmp) != 0) {
      FreePool (Tmp);
      break;
    }

    Want = (UINT32)Len - Done;
    Chunk = UFS_CHUNK_BLOCKS * 4096 - InBlk;
    if (Chunk > Want) {
      Chunk = Want;
    }
    CopyMem (Data + Done, Tmp + InBlk, Chunk);
    Done += Chunk;
    FreePool (Tmp);
  }

  if (Done != (UINT32)Len) {
    if (Log != NULL) {
      Log ("UFS SHORT", (UINT64)Done);
    }
    return EFI_DEVICE_ERROR;
  }

  if (Log != NULL) {
    Log ("UFS OK", (UINT64)Len);
  }
  *Buf  = Data;
  *Size = (UINTN)Len;
  return EFI_SUCCESS;
}

'''
    t = t.replace("EFI_STATUS\nXnuLoadFromBlock (", add + "EFI_STATUS\nXnuLoadFromBlock (", 1)
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("XnuLoad.c 已加 UFS 兜底")
else:
    print("XnuLoad.c 已有 UFS")

# ---------- 2) Probe.c：块设备失败后再试 UFS ----------
Q = r"E:\ios-on-fuxi\loader\Probe.c"
c = io.open(Q, encoding="utf-8").read()

c = c.replace(
    "extern EFI_STATUS   XnuLoadFromBlock (VOID **Buf, UINTN *Size,",
    "extern EFI_STATUS   XnuLoadFromUfs (VOID **Buf, UINTN *Size,\n"
    "                                    VOID (*Log)(CONST CHAR8 *, UINT64));\n"
    "extern EFI_STATUS   XnuLoadFromBlock (VOID **Buf, UINTN *Size,",
    1,
)

c = c.replace(
    """      XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      XnuScreenLog ("BUF SIZE", mXnuBufSize);""",
    """      XnuLoadFromBlock (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      if (mXnuBufSize == 0) {
        XnuScreenLog ("BLK EMPTY, TRY UFS", 0);
        XnuLoadFromUfs (&mXnuBuf, &mXnuBufSize, XnuScreenLog);
      }
      XnuScreenLog ("BUF SIZE", mXnuBufSize);""",
    1,
)
io.open(Q, "w", encoding="utf-8", newline="\n").write(c)
print("Probe.c 已接 UFS 兜底")

# ---------- 3) INF ----------
inf = r"E:\ios-on-fuxi\loader\Probe.inf"
s = io.open(inf, encoding="utf-8").read()
if "XnuUfs.c" not in s:
    s = s.replace("  XnuLoad.c\n", "  XnuLoad.c\n  XnuUfs.c\n")
    io.open(inf, "w", encoding="utf-8", newline="\n").write(s)
    print("INF 已加 XnuUfs.c")

# ---------- 4) CI 复制列表 ----------
W = r"E:\ios-on-fuxi\.github\workflows\build-fuxi-uefi.yml"
w = io.open(W, encoding="utf-8").read()
w = w.replace(
    "             loader/XnuBoot.c loader/XnuLoad.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
    "             loader/XnuBoot.c loader/XnuLoad.c loader/XnuUfs.c loader/xnu_jump.S loader/xnu_payload.S \"$probe\"/",
)
io.open(W, "w", encoding="utf-8", newline="\n").write(w)
print("CI 复制列表已更新")
