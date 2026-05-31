"""探测脚本 2:用 probe_login 产出的 cookie 实测 msglist 接口,沉淀真实样例。

用法:
    python scripts/probe_msglist.py [host_uin]

不传 host_uin 时抓"自己"(最安全)。产出:
- scripts/msglist_raw.json   接口原始返回(完整)

目的:确认真实接口域名/参数/返回字段名(tid/content/时间/pic/commentlist 等),
据此校正 qqfetch/qzone/parser.py 与 image_urls.py;脱敏后可另存为
tests/fixtures/msglist_sample.json 驱动单测。
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from qqfetch.auth.qrlogin import extract_uin  # noqa: E402
from qqfetch.crypto import g_tk  # noqa: E402

MSGLIST = "https://h5.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    cookie_file = Path(__file__).parent / "probe_cookies.json"
    if not cookie_file.exists():
        print("未找到 probe_cookies.json,请先运行 probe_login.py。")
        return 1
    cookies = json.loads(cookie_file.read_text(encoding="utf-8"))
    uin = extract_uin(cookies)
    host = int(sys.argv[1]) if len(sys.argv) > 1 else uin
    gtk = g_tk(cookies.get("p_skey"), cookies.get("skey"))
    print(f"uin={uin} host={host} g_tk={gtk}")

    client = httpx.Client(
        cookies=cookies,
        timeout=15,
        headers={"User-Agent": UA, "Referer": f"https://user.qzone.qq.com/{uin}"},
    )
    params = {
        "uin": uin, "hostUin": host, "pos": 0, "num": 10, "g_tk": gtk,
        "format": "json", "inCharset": "utf-8", "outCharset": "utf-8",
        "code_version": 1, "need_private_comment": 1, "replynum": 100, "sort": 0,
    }
    r = client.get(MSGLIST, params=params)
    print("HTTP", r.status_code, "正文长度", len(r.text))
    print("前 500 字符:\n", r.text[:500])

    text = r.text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else {}

    out = Path(__file__).parent / "msglist_raw.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已保存原始返回:", out)

    msglist = data.get("msglist") or []
    print(f"code={data.get('code')} total={data.get('total')} msglist 条数={len(msglist)}")
    if msglist:
        first = msglist[0]
        print("首条字段名:", sorted(first.keys()))
        if first.get("pic"):
            print("pic[0] 字段名:", sorted(first["pic"][0].keys()))
        if first.get("commentlist"):
            print("comment[0] 字段名:", sorted(first["commentlist"][0].keys()))
    print(
        "\n请核对上面字段名是否与 parser.py / image_urls.py 的兜底键一致;"
        "如有差异,据实校正,并把脱敏后的 msglist_raw.json 另存为 "
        "tests/fixtures/msglist_sample.json。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
