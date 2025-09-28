# AWS 構文パロディ・ジェネレーター

任意の単語や用語（例: コーヒーポッド）を入力すると、AWS 公式ドキュメント風のパロディ解説ページを生成する Flask 製ウェブアプリケーションです。実際の AWS サービスとは無関係な架空サービスを「フルマネージド」「高可用性」といった AWS らしい表現で紹介し、API とブラウザ UI の両方から利用できます。

## 主な特徴
- ✅ 単語 1 つでパロディ AWS サービス仕様を丸ごと生成
- ✅ 日本語 / 英語、および盛り具合（standard / overkill）の切り替えに対応
- ✅ OpenAI API が利用可能な場合は LLM 生成、未設定でもサンプル JSON を返すフォールバックを実装
- ✅ Flask + Vanilla JS + CSS のシンプル構成でローカル実行が容易

## アーキテクチャ概要
```
+-------------+       POST /api/generate       +---------------------+
| ブラウザ UI | -----------------------------> | Flask API (app.py)  |
| (templates/ |                                |  - Prompt 組み立て  |
|  static/)   | <----------------------------- |  - LLM 呼び出し     |
+-------------+         JSON レスポンス        |  - JSON 検証        |
                                                 +---------------------+
```

- `app.py`: Flask アプリ本体。`/` でフロントページ、`/api/generate` で JSON API を提供。
- `templates/index.html`: 入力フォームおよび生成結果を表示する SPA 風の 1 ページ。
- `static/`: CSS・JavaScript・画像などの静的ファイル。
- `DummyLLMClient`: OpenAI API を利用できない環境向けの擬似レスポンス生成クラス。

## 動作要件
- Python 3.9 以上推奨
- pip / venv 等の一般的な Python ツールチェーン
- （任意）OpenAI API キー

## セットアップ手順
1. リポジトリを取得
   ```bash
   git clone <このリポジトリの URL>
   cd aws_parody_page
   ```
2. 仮想環境を作成し依存関係をインストール
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows の場合: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. 必要に応じて環境変数を設定
   ```bash
   # OpenAI API を利用する場合のみ必須
   export OPENAI_API_KEY="sk-..."
   export OPENAI_MODEL="gpt-4o-mini"  # 省略時は gpt-4o-mini
   ```
   `OPENAI_API_KEY` が未設定の場合は `DummyLLMClient` がダミー JSON を返します。

4. ローカル開発サーバーを起動
   ```bash
   flask --app app run --debug  # デフォルト: http://127.0.0.1:5000
   ```

## 使い方
### ブラウザ UI
1. `http://127.0.0.1:5000/` にアクセス。
2. 任意の単語、言語、トーンを入力し「生成する」をクリック。
3. 画面下部に AWS 風の解説ページがレンダリングされます。

### API 経由
`/api/generate` に対して JSON を POST すると、同じ内容を JSON で取得できます。
```bash
curl -s \
  -X POST http://127.0.0.1:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"term": "コーヒーポッド", "lang": "ja", "tone": "standard"}' |
  jq
```
レスポンス例（抜粋）:
```json
{
  "service_name": "AWS Elastic コーヒーポッド",
  "tagline": "コーヒーポッドを、クラウド級の可用性で。",
  "summary": "AWS Elastic コーヒーポッド は...",
  "highlights": [
    "フルマネージドで運用負荷を大幅削減",
    "需要に応じた自動スケーリング",
    "IAM と統合したロールベースアクセス制御"
  ],
  ...
}
```

## 環境変数と設定
| 変数名 | デフォルト | 説明 |
| ------ | ---------- | ---- |
| `OPENAI_API_KEY` | なし | OpenAI API キー。未設定の場合はダミー応答にフォールバック |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI LLM 呼び出し時のモデル名 |
| `PORT` | `5000` | `python app.py` 実行時のポート番号 |

`.env` を作成すると自動的に読み込まれます（`python-dotenv` 利用）。

## 開発者向けメモ
- コードスタイルは PEP 8 をベースにしつつ、日本語コメントを多用しています。
- `ServiceSpec` (Pydantic) で LLM からの JSON をバリデーションしているため、スキーマ変更時はモデル定義を更新してください。
- 静的ファイルのビルド工程はなく、すべて手動管理です。必要に応じてフロントエンドツールチェーンを導入してください。

## ライセンス
本リポジトリは [MIT License](./LICENSE) の下で公開されています。
