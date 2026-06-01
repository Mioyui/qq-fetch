CREATE SCHEMA IF NOT EXISTS __QQFETCH_SCHEMA__;

CREATE TABLE IF NOT EXISTS __QQFETCH_SCHEMA__.qqfetch_shuoshuo (
    target_qq BIGINT NOT NULL,
    tid TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_time BIGINT NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    raw JSONB NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (target_qq, tid)
);

CREATE TABLE IF NOT EXISTS __QQFETCH_SCHEMA__.qqfetch_comment (
    target_qq BIGINT NOT NULL,
    tid TEXT NOT NULL,
    comment_key TEXT NOT NULL,
    comment_id TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    created_time BIGINT NOT NULL DEFAULT 0,
    author_uin TEXT NOT NULL DEFAULT '',
    author_name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (target_qq, tid, comment_key),
    CONSTRAINT fk_qqfetch_comment_shuoshuo
        FOREIGN KEY (target_qq, tid)
        REFERENCES __QQFETCH_SCHEMA__.qqfetch_shuoshuo(target_qq, tid)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS __QQFETCH_SCHEMA__.qqfetch_picture (
    target_qq BIGINT NOT NULL,
    tid TEXT NOT NULL,
    pic_id TEXT NOT NULL,
    url TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    sort_index INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (target_qq, tid, pic_id),
    CONSTRAINT fk_qqfetch_picture_shuoshuo
        FOREIGN KEY (target_qq, tid)
        REFERENCES __QQFETCH_SCHEMA__.qqfetch_shuoshuo(target_qq, tid)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_qqfetch_shuoshuo_target_created
    ON __QQFETCH_SCHEMA__.qqfetch_shuoshuo(target_qq, created_time DESC);

CREATE INDEX IF NOT EXISTS idx_qqfetch_comment_target_tid
    ON __QQFETCH_SCHEMA__.qqfetch_comment(target_qq, tid);

CREATE INDEX IF NOT EXISTS idx_qqfetch_picture_target_tid
    ON __QQFETCH_SCHEMA__.qqfetch_picture(target_qq, tid);
