"""ImageDownloader 单测:命名、魔数扩展名、跨实例去重、失败记录、并发。

用 FakeHttp 提供预设字节,不触网。
"""

from __future__ import annotations

from qqfetch.download.image_downloader import ImageDownloader
from qqfetch.models import Picture, Shuoshuo

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 10
JPG = b"\xff\xd8\xff" + b"0" * 10


class FakeHttp:
    def __init__(self, data_map, fail=None):
        self.data_map = data_map
        self.fail = fail or set()
        self.calls = []

    def get_bytes(self, url, referer=None, throttle=True):
        self.calls.append(url)
        if url in self.fail:
            raise RuntimeError("boom")
        return self.data_map.get(url, JPG)


def _sh(tid, pics):
    return Shuoshuo(tid=tid, content="", created_time=0, pictures=pics)


def test_downloads_and_names_by_url_ext(tmp_path):
    http = FakeHttp({"http://a/1.png": PNG})
    res = ImageDownloader(http, tmp_path).download_for(
        _sh("t1", [Picture(pic_id="p1", url="http://a/1.png")])
    )
    assert res[0].ok
    assert (tmp_path / "t1_0.png").read_bytes() == PNG


def test_ext_guess_by_magic_when_no_suffix(tmp_path):
    http = FakeHttp({"http://a/noext": PNG})
    ImageDownloader(http, tmp_path).download_for(
        _sh("t", [Picture(pic_id="p", url="http://a/noext")])
    )
    assert (tmp_path / "t_0.png").exists()      # 无后缀,靠魔数判定 png


def test_dedup_skips_within_run(tmp_path):
    http = FakeHttp({"http://a/1.jpg": JPG})
    d = ImageDownloader(http, tmp_path)
    pic = Picture(pic_id="p1", url="http://a/1.jpg")
    d.download_for(_sh("t1", [pic]))
    d.download_for(_sh("t1", [pic]))
    assert http.calls.count("http://a/1.jpg") == 1


def test_dedup_persists_across_instances(tmp_path):
    pic = Picture(pic_id="p", url="http://a/1.jpg")
    ImageDownloader(FakeHttp({"http://a/1.jpg": JPG}), tmp_path).download_for(_sh("t", [pic]))
    http2 = FakeHttp({"http://a/1.jpg": JPG})
    ImageDownloader(http2, tmp_path).download_for(_sh("t", [pic]))
    assert http2.calls == []                    # 新实例读 .index 后跳过


def test_failure_is_recorded_not_raised(tmp_path):
    http = FakeHttp({}, fail={"http://a/x.jpg"})
    res = ImageDownloader(http, tmp_path).download_for(
        _sh("t", [Picture(pic_id="p", url="http://a/x.jpg")])
    )
    assert not res[0].ok and res[0].error
    assert (tmp_path / "failed_images.log").exists()


def test_concurrent_download(tmp_path):
    http = FakeHttp({f"http://a/{i}.jpg": JPG for i in range(5)})
    pics = [Picture(pic_id=f"p{i}", url=f"http://a/{i}.jpg") for i in range(5)]
    res = ImageDownloader(http, tmp_path, concurrency=3).download_for(_sh("t", pics))
    assert len(res) == 5 and all(r.ok for r in res)
