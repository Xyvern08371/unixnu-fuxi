import io

p = r"E:\ios-on-fuxi\.github\workflows\build-xnu-macos.yml"
t = io.open(p, encoding="utf-8").read()

OLD_TAIL = """          python3 - "$F" <<'PY'
          import sys, io
          p = sys.argv[1]
          t = io.open(p, encoding='utf-8').read()
          if '_open(' in t:
              print('already patched'); raise SystemExit(0)
          t = t.replace(
              "import urllib.request\\n",
              "import urllib.request\\n"
              "_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''\\n"
              "def _open(url, timeout=30):\\n"
              "    req = urllib.request.Request(url)\\n"
              "    if _TOKEN:\\n"
              "        req.add_header('Authorization', 'Bearer ' + _TOKEN)\\n"
              "    req.add_header('User-Agent', 'unixnu-build')\\n"
              "    return urllib.request.urlopen(req, timeout=timeout)\\n",
              1)
          t = t.replace("urllib.request.urlopen(URL, timeout=30).read()", "_open(URL).read()")
          t = t.replace("urllib.request.urlopen(entry['download_url'], timeout=30).read()",
                        "_open(entry['download_url']).read()")
          t = t.replace("urllib.request.urlopen(crypto_url, timeout=30).read()", "_open(crypto_url).read()")
          t = t.replace("urllib.request.urlopen(url, timeout=30).read()", "_open(url).read()")
          io.open(p, 'w', encoding='utf-8').write(t)
          print('patched', p)
          PY
          grep -n "_open\\|_TOKEN" "$F" | head -20 || true"""

NEW_TAIL = """          # 关键：重写 restore()，用 git/blobs API 拉文件内容。
          # 原来的实现是 _open(entry['download_url'])，那是
          # raw.githubusercontent.com，token 对它无效、也有匿名限额，
          # 第 15 次跑就是在这里 HTTPError 403。
          # git/blobs 走 api.github.com，Bearer token 生效（5000/h）。
          python3 - "$F" <<'PY'
          import sys, io
          p = sys.argv[1]
          t = io.open(p, encoding='utf-8').read()
          if 'git-blobs-v2' in t:
              print('already patched'); raise SystemExit(0)

          # 1) 在 import 区后插入 _blob_fetch
          t = t.replace(
              "import urllib.request\\n",
              "import urllib.request\\n"
              "_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''\\n"
              "def _open(url, timeout=60):\\n"
              "    req = urllib.request.Request(url)\\n"
              "    if _TOKEN:\\n"
              "        req.add_header('Authorization', 'Bearer ' + _TOKEN)\\n"
              "    req.add_header('User-Agent', 'unixnu-build')\\n"
              "    req.add_header('Accept', 'application/vnd.github+json')\\n"
              "    return urllib.request.urlopen(req, timeout=timeout)\\n"
              "def _blob_fetch(sha, repo='apple-oss-distributions/xnu'):\\n"
              "    # git-blobs-v2: fetch by blob sha through the API so the token applies\\n"
              "    import base64, json as _json\\n"
              "    url = 'https://api.github.com/repos/' + repo + '/git/blobs/' + sha\\n"
              "    doc = _json.loads(_open(url).read())\\n"
              "    return base64.b64decode(doc['content'])\\n",
              1)

          # 2) restore() 里把 download_url 换成 _blob_fetch(entry['sha'])
          t = t.replace(
              "data = urllib.request.urlopen(_request(entry['download_url']), timeout=30).read()",
              "data = _blob_fetch(entry['sha'])")

          # 3) 其余 urlopen / _request 调用统一走 _open
          t = t.replace("urllib.request.urlopen(_request(URL), timeout=30).read()", "_open(URL).read()")
          t = t.replace("urllib.request.urlopen(_request(crypto_url), timeout=30).read()", "_open(crypto_url).read()")
          t = t.replace("urllib.request.urlopen(_request(url), timeout=30).read()", "_open(url).read()")

          io.open(p, 'w', encoding='utf-8').write(t)
          print('patched', p)
          PY
          echo "--- 补丁后的关键行 ---"
          grep -n "_open\\|_blob_fetch\\|download_url" "$F" | head -20 || true"""

if OLD_TAIL in t:
    t = t.replace(OLD_TAIL, NEW_TAIL, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("已改成 git/blobs API 拉取")
else:
    print("锚点没找到")
    i = t.find("给 prepare-xnu-source.py 加 API token")
    print(repr(t[i:i + 400]))

import yaml
yaml.safe_load(io.open(p, encoding="utf-8"))
print("YAML 有效")
