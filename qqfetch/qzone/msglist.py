"""说说列表分页编排:从断点续抓,逐页解析、去重、落盘,并以多重条件终止。"""

from __future__ import annotations

from typing import Callable, Iterator, Optional

from ..logging_setup import get_logger
from ..models import Shuoshuo
from .parser import parse_msglist

_log = get_logger(__name__)


class MsglistFetcher:
    """把 QzoneClient + Repository + Checkpoint 编排为可续传的分页抓取。"""

    def __init__(
        self,
        client,
        repo,
        checkpoint,
        *,
        page_size: int = 20,
        max_count: int = 0,
        prefer_original: bool = True,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self._client = client
        self._repo = repo
        self._cp = checkpoint
        self._page_size = page_size
        self._max_count = max_count          # 0 表示不限本次新增条数
        self._prefer_original = prefer_original
        self._on_page = on_page              # 回调(pos, total),用于进度展示

    def fetch_all(self, host_uin: int) -> Iterator[Shuoshuo]:
        """生成器:逐条产出本次新增的说说;调用方消费时可顺带下载图片。"""
        pos = self._cp.pos
        fetched = 0
        consecutive_no_new = 0
        while True:
            payload = self._client.call_msglist(host_uin, pos, self._page_size)
            page = parse_msglist(payload, prefer_original=self._prefer_original)
            if self._on_page:
                self._on_page(pos, page.total)
            if not page.items:
                break

            new_in_page = 0
            page_tids = []
            for sh in page.items:
                page_tids.append(sh.tid)
                # 断点已见过的 tid 直接跳过;仓储内是否首次入库由 save() 自己判断。
                if self._cp.seen(sh.tid):
                    continue
                is_new = self._repo.save(sh)
                if is_new:
                    new_in_page += 1
                    fetched += 1
                    yield sh
                if self._max_count and fetched >= self._max_count:
                    self._cp.advance(pos + len(page.items), page_tids)
                    return

            pos += len(page.items)
            self._cp.advance(pos, page_tids)

            if page.total and pos >= page.total:
                break
            # 防回环兜底:连续两页无任何新内容则停止(应对 total 缺失或循环返回)
            if new_in_page == 0:
                consecutive_no_new += 1
                if consecutive_no_new >= 2:
                    _log.info("连续多页无新内容,停止抓取")
                    break
            else:
                consecutive_no_new = 0
