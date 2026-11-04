import io
import re
import sys

sys.path.insert(0, r"E:\ios-on-fuxi\tools")
import _add_lowercase as G   # 复用字形表（该模块 main() 只在 __main__ 下运行）

GLY = dict(G.LOWER_GLYPHS)
GLY.update(G.EXTRA)


def rows_in_block(lines, start):
    """返回 FONT 块里的数据行数（不含收尾的 };）"""
    end = next(i for i in range(start, len(lines)) if lines[i].strip().startswith("};"))
    return end, end - start - 1


def fix(path):
    s = io.open(path, encoding="utf-8").read()
    m = re.search(r'CHARSET\[\] = "([^"]*)"', s)
    if not m:
        print("%s: 没有 CHARSET" % path)
        return
    charset = m.group(1)

    lines = s.split("\n")
    start = next((i for i, l in enumerate(lines) if "FONT[][8]" in l), -1)
    if start < 0:
        print("%s: 没有 FONT" % path)
        return
    end, have = rows_in_block(lines, start)
    need = len(charset) - have
    print("%s: 字符=%d 字形=%d 需要补=%d" % (path, len(charset), have, need))
    if need <= 0:
        return

    # 已经出现过的字符（按注释/顺序无法精确判断），这里按 charset 末尾补齐
    new_rows = []
    for c in charset[have:]:
        g = GLY.get(c)
        if g is None:
            print("  警告: 缺少字形 %r，用空格代替" % c)
            g = (0, 0, 0, 0, 0, 0, 0, 0)
        new_rows.append("  { " + ",".join("0x%02X" % b for b in g) + " }, /* %s */" % c)

    lines[end:end] = new_rows
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("  已插入 %d 行" % len(new_rows))


def verify(path):
    s = io.open(path, encoding="utf-8").read()
    charset = re.search(r'CHARSET\[\] = "([^"]*)"', s).group(1)
    lines = s.split("\n")
    start = next((i for i, l in enumerate(lines) if "FONT[][8]" in l), -1)
    end, have = rows_in_block(lines, start)
    ok = len(charset) == have
    print("%-22s 字符=%d 字形=%d %s" % (path, len(charset), have, "OK" if ok else "!! 不匹配"))
    return ok


if __name__ == "__main__":
    files = [r"E:\ios-on-fuxi\loader\Probe.c", r"E:\ios-on-fuxi\payload\kernel.c"]
    for f in files:
        fix(f)
    print()
    all_ok = all(verify(f) for f in files)
    sys.exit(0 if all_ok else 1)
