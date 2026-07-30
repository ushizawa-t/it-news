#!/usr/bin/env python3
"""RSSフィードを巡回し、新着記事をSlackに通知する。

使い方:
    python check_feeds.py --dry-run   # Slackに送らず標準出力に表示
    python check_feeds.py             # 新着があればSlackに通知(要 SLACK_WEBHOOK_URL)

state.json に通知済み記事のIDを保存し、重複通知を防ぐ。
フィード初回チェック時は既存記事を既読として登録するだけで通知しない
(過去記事が一斉に流れるのを防ぐため)。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

BASE_DIR = Path(__file__).resolve().parent
FEEDS_FILE = BASE_DIR / "feeds.json"
STATE_FILE = BASE_DIR / "state.json"

MAX_ITEMS_PER_FEED = 10       # 1フィードあたりの1回の最大通知数
MAX_SEEN_IDS_PER_FEED = 300   # stateに保持する既読IDの上限
MAX_AGE_DAYS = 3              # これより古い記事は新着扱いしない
USER_AGENT = "it-news-notifier/1.0 (+https://github.com)"
JST = timezone(timedelta(hours=9))


def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def entry_id(entry):
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def entry_published(entry):
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


def fetch_new_entries(feed_conf, state):
    """フィードを取得し、(新着エントリのリスト, 通知するかどうか) を返す。"""
    url = feed_conf["url"]
    parsed = feedparser.parse(url, agent=USER_AGENT)

    if parsed.bozo and not parsed.entries:
        print(f"  WARN: {feed_conf['name']} の取得に失敗: {parsed.bozo_exception}", file=sys.stderr)
        return [], False

    seen = state.get(url)
    first_run = seen is None
    seen_set = set(seen or [])

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    new_entries = []
    for entry in parsed.entries:
        eid = entry_id(entry)
        if not eid or eid in seen_set:
            continue
        published = entry_published(entry)
        if published and published < cutoff:
            seen_set.add(eid)
            continue
        new_entries.append(entry)
        seen_set.add(eid)

    # 既読IDリストを更新(新しいものを末尾に、上限超過分は古い方から削除)
    updated = (seen or []) + [entry_id(e) for e in parsed.entries if entry_id(e) and entry_id(e) not in (seen or [])]
    state[url] = updated[-MAX_SEEN_IDS_PER_FEED:]

    if first_run:
        print(f"  INIT: {feed_conf['name']} 初回のため {len(parsed.entries)} 件を既読登録(通知なし)")
        return [], False

    new_entries.sort(key=lambda e: entry_published(e) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return new_entries[:MAX_ITEMS_PER_FEED], True


def build_slack_message(results):
    """カテゴリ別にまとめたSlack用テキストを組み立てる。"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    lines = [f":newspaper: *テックブログ新着記事 ({today})*"]

    by_category = {}
    for feed_conf, entries in results:
        by_category.setdefault(feed_conf["category"], []).append((feed_conf, entries))

    for category, feeds in by_category.items():
        lines.append(f"\n*── {category} ──*")
        for feed_conf, entries in feeds:
            for entry in entries:
                title = entry.get("title", "(no title)").strip()
                link = entry.get("link", "")
                lines.append(f"• <{link}|{title}>  _({feed_conf['name']})_")

    return "\n".join(lines)


def post_to_slack(text, webhook_url):
    resp = requests.post(webhook_url, json={"text": text}, timeout=30)
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Slackに送信せず標準出力に表示")
    args = parser.parse_args()

    feeds = load_json(FEEDS_FILE, [])
    state = load_json(STATE_FILE, {})

    results = []
    for feed_conf in feeds:
        print(f"checking: {feed_conf['name']}")
        entries, notify = fetch_new_entries(feed_conf, state)
        if notify and entries:
            results.append((feed_conf, entries))

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    total = sum(len(e) for _, e in results)
    if total == 0:
        print("新着記事はありませんでした。")
        return

    message = build_slack_message(results)
    print(f"\n新着 {total} 件:")

    if args.dry_run:
        print("\n--- Slackメッセージ(dry-run) ---")
        print(message)
        return

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: 環境変数 SLACK_WEBHOOK_URL が未設定です。", file=sys.stderr)
        sys.exit(1)

    post_to_slack(message, webhook_url)
    print("Slackに通知しました。")


if __name__ == "__main__":
    main()
