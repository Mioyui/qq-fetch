"""探测脚本 1:实测扫码登录全流程,打印原始响应与 cookie,用于校正主实现。

用法:
    python scripts/probe_login.py

需要用手机 QQ 扫描生成的二维码。产出:
- scripts/qr.png            二维码图片(请扫描)
- scripts/probe_cookies.json 登录成功后的完整 cookie(供 probe_msglist.py 使用)

目的:实测 ptqrshow 参数、ptuiCB 回调格式、check_sig 重定向链与最终 cookie 键名,
据此校正 qqfetch/auth/qrlogin.py。
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from qqfetch.auth.qrlogin import parse_ptuicb  # noqa: E402
from qqfetch.crypto import ptqrtoken  # noqa: E402

APPID = 549000912
PTQRSHOW = "https://ssl.ptlogin2.qq.com/ptqrshow"
PTQRLOGIN = "https://ssl.ptlogin2.qq.com/ptqrlogin"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    client = httpx.Client(
        follow_redirects=False,
        timeout=15,
        headers={"User-Agent": UA, "Referer": "https://xui.ptlogin2.qq.com/"},
    )

    # 1) 出码
    r = client.get(
        PTQRSHOW,
        params={"appid": APPID, "e": "2", "l": "M", "s": "3", "d": "72",
                "v": "4", "t": str(time.time()), "daid": "5", "pt_3rd_aid": "0"},
    )
    qrsig = client.cookies.get("qrsig") or r.cookies.get("qrsig")
    if not qrsig:
        print("未拿到 qrsig,出码失败。响应头:", dict(r.headers))
        return 1
    print("qrsig =", qrsig)
    qr_path = Path(__file__).parent / "qr.png"
    qr_path.write_bytes(r.content)
    print(f"二维码已保存:{qr_path} —— 请用手机 QQ 扫描并确认")
    token = ptqrtoken(qrsig)
    print("ptqrtoken =", token)

    # 2) 轮询
    check_url = None
    for _ in range(60):
        params = {
            "u1": "https://qzone.qq.com/", "ptqrtoken": str(token), "ptredirect": "0",
            "h": "1", "t": "1", "g": "1", "from_ui": "1", "ptlang": "2052",
            "action": "0-0-" + str(int(time.time() * 1000)), "js_ver": "20102616",
            "js_type": "1", "login_sig": "", "pt_uistyle": "40", "aid": APPID, "daid": "5",
        }
        resp = client.get(PTQRLOGIN, params=params)
        print("ptuiCB raw:", resp.text.strip())
        res = parse_ptuicb(resp.text)
        print(f"  解析 -> code={res.code} msg={res.message!r} nick={res.nickname!r}")
        if res.is_success:
            check_url = res.check_sig_url
            break
        if res.is_expired:
            print("二维码已过期,请重新运行。")
            return 1
        time.sleep(2)

    if not check_url:
        print("超时未完成登录。")
        return 1
    print("check_sig URL =", check_url)

    # 3) finalize:逐跳打印重定向与 set-cookie
    resp = client.get(check_url, follow_redirects=False)
    hops = 0
    while resp.status_code in (301, 302, 303, 307, 308) and hops < 10:
        print(f"[hop {hops}] {resp.status_code} -> {resp.headers.get('location')}")
        for sc in resp.headers.get_list("set-cookie"):
            print("   set-cookie:", sc.split(";")[0])
        resp = client.get(resp.headers["location"], follow_redirects=False)
        hops += 1

    print("最终 cookies:")
    for k, v in client.cookies.items():
        shown = v if len(v) <= 40 else v[:40] + "..."
        print(f"  {k} = {shown}")

    out = Path(__file__).parent / "probe_cookies.json"
    out.write_text(json.dumps(dict(client.cookies), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cookie 已保存:{out}(供 probe_msglist.py 使用)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
