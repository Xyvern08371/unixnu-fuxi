import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

anchor = "      - name: 第 1 步 - 编 XNU 基线（产出 cpo.json）"

inject = r'''      # prepare-xnu-source.py 用匿名 GitHub API 取 DriverKit 头文件清单，
      # 匿名限额每小时 60 次，跑几次就 403 rate limit exceeded。
      # 这里给它的 urllib 调用加 Authorization 头（GITHUB_TOKEN 限额 5000/h）。
      - name: 给 prepare-xnu-source.py 加 API token
        if: ${{ !env.SKIP_TOKEN_PATCH }}
        run: |
          set -euxo pipefail
          F=UniXNU/scripts/prepare-xnu-source.py
          cp "$F" "$F.orig"
          python3 - "$F" <<'PY'
          import sys, io
          p = sys.argv[1]
          t = io.open(p, encoding='utf-8').read()
          if '_open(' in t:
              print('already patched'); raise SystemExit(0)
          t = t.replace(
              "import urllib.request\n",
              "import urllib.request\n"
              "_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''\n"
              "def _open(url, timeout=30):\n"
              "    req = urllib.request.Request(url)\n"
              "    if _TOKEN:\n"
              "        req.add_header('Authorization', 'Bearer ' + _TOKEN)\n"
              "    req.add_header('User-Agent', 'unixnu-build')\n"
              "    return urllib.request.urlopen(req, timeout=timeout)\n",
              1)
          t = t.replace("urllib.request.urlopen(URL, timeout=30).read()", "_open(URL).read()")
          t = t.replace("urllib.request.urlopen(entry['download_url'], timeout=30).read()",
                        "_open(entry['download_url']).read()")
          t = t.replace("urllib.request.urlopen(crypto_url, timeout=30).read()", "_open(crypto_url).read()")
          t = t.replace("urllib.request.urlopen(url, timeout=30).read()", "_open(url).read()")
          io.open(p, 'w', encoding='utf-8').write(t)
          print('patched', p)
          PY
          grep -n "_open\|_TOKEN" "$F" | head -20 || true

'''

if anchor in t and "加 API token" not in t:
    t = t.replace(anchor, inject + anchor, 1)
    print("已插入")
else:
    print("锚点:", "已存在" if "加 API token" in t else "找不到")

io.open(p, "w", encoding="utf-8", newline="\n").write(t)

import yaml
d = yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效，steps:")
for s in d["jobs"]["build"]["steps"]:
    print("  -", s.get("name", s.get("uses", "?")))
