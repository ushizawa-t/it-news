# it-news

Web開発・システムプログラミング系のテックブログを毎日巡回し、新着記事をSlackに通知するツール。

## 仕組み

- [feeds.json](feeds.json) に登録したRSS/Atomフィードを巡回
- 通知済み記事のIDを [state.json](state.json) に記録し、重複通知を防止
- 新着があればSlack Incoming Webhookでカテゴリ別にまとめて通知
- GitHub Actionsで毎日 09:00 JST に自動実行

各フィードの初回チェック時は既存記事を既読として登録するだけで通知しません(過去記事の一斉通知を防ぐため)。3日より古い記事も通知対象外です。

## セットアップ

### 1. Slack Incoming Webhookの作成

1. https://api.slack.com/apps で新規アプリを作成(From scratch)
2. 「Incoming Webhooks」を有効化し、通知先チャンネルを選んでWebhook URLを発行
3. `https://hooks.slack.com/services/...` 形式のURLを控える

### 2. GitHubリポジトリの設定

1. このリポジトリをGitHubにpush
2. リポジトリの Settings → Secrets and variables → Actions で
   `SLACK_WEBHOOK_URL` という名前のSecretにWebhook URLを登録

以降、毎日 09:00 JST に自動実行されます。Actionsタブの「Tech blog Slack notifier」から手動実行(Run workflow)も可能です。

## ローカルでの実行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Slackに送らず内容を確認
python check_feeds.py --dry-run

# 実際に通知する
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
python check_feeds.py
```

## フィードの追加・削除

[feeds.json](feeds.json) を編集してください。各エントリは以下の形式です:

```json
{
  "name": "表示名",
  "url": "https://example.com/feed.xml",
  "category": "Web開発"
}
```

## 調整可能なパラメータ

[check_feeds.py](check_feeds.py) 冒頭の定数で調整できます:

- `MAX_ITEMS_PER_FEED` — 1フィードあたりの1回の最大通知数(既定: 10)
- `MAX_AGE_DAYS` — これより古い記事は通知しない(既定: 3日)
- 実行時刻は [.github/workflows/notify.yml](.github/workflows/notify.yml) のcron(UTC)で変更
