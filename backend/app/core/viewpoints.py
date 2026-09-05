"""AI推奨事項の下敷きになる観点カタログ。

SKILL.md「5. 画面設計標準の重点観点」「6. 詳細設計標準の重点観点」と、
STEP 5 の品質観点から起こした一般的なレビュー観点。

**ここにあるものは標準書由来ではない。** 標準書がその観点に触れていない場合に
「標準書に規定が無い観点」として提案するためだけに使う (必須原則 8)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Viewpoint:
    key: str
    category: str
    sub_category: str
    check_point: str
    severity: str
    #: 標準書側にこの観点があるかを調べるための語。1つでも当たれば「規定あり」とみなす。
    keywords: tuple[str, ...]


#: 文書種別ごとの観点。SKILL.md 5章・6章の並びをそのまま観点キーにしている。
VIEWPOINTS: dict[str, tuple[Viewpoint, ...]] = {
    "screen": (
        Viewpoint("screen-id", "UI", "画面ID", "画面IDの採番規則が定義されているか？", "Medium", ("画面ID", "画面番号")),
        Viewpoint("screen-name", "UI", "画面名称", "画面名称の記述ルールが定義されているか？", "Low", ("画面名称", "画面名")),
        Viewpoint("layout", "UI", "レイアウト", "画面レイアウトの表現方法が定義されているか？", "Medium", ("レイアウト", "画面イメージ")),
        Viewpoint("item-id", "UI", "項目ID", "画面項目の項目IDが定義されているか？", "High", ("項目ID",)),
        Viewpoint("item-type", "UI", "データ型", "画面項目のデータ型と桁数が定義されているか？", "High", ("データ型", "桁数")),
        Viewpoint("required", "入力", "必須/任意", "画面項目の必須・任意区分が定義されているか？", "High", ("必須", "任意区分")),
        Viewpoint("default-value", "UI", "初期値", "画面項目の初期値が定義されているか？", "Medium", ("初期値", "デフォルト")),
        Viewpoint("enabled", "UI", "活性/非活性", "項目の活性・非活性の条件が定義されているか？", "Medium", ("活性", "非活性")),
        Viewpoint("visible", "UI", "表示/非表示", "項目の表示・非表示の条件が定義されているか？", "Medium", ("表示", "非表示")),
        Viewpoint("input-control", "入力", "入力制御", "入力制御（IME・最大長など）が定義されているか？", "Medium", ("入力制御", "IME", "最大長")),
        Viewpoint("validation", "入力", "入力チェック", "入力チェックの内容が定義されているか？", "High", ("入力チェック", "バリデーション", "妥当性")),
        Viewpoint("button", "UI", "ボタン", "ボタンの配置と機能が定義されているか？", "Medium", ("ボタン",)),
        Viewpoint("event", "UI", "イベント", "画面イベントと処理の対応が定義されているか？", "Medium", ("イベント", "押下")),
        Viewpoint("transition", "UI", "画面遷移", "画面遷移と遷移条件が定義されているか？", "High", ("画面遷移", "遷移")),
        Viewpoint("message", "UI", "メッセージ", "メッセージの管理方法が定義されているか？", "Medium", ("メッセージ",)),
        Viewpoint("error-display", "エラー処理", "エラー表示", "エラー時の表示方法が定義されているか？", "High", ("エラー表示", "エラー時")),
        Viewpoint("authz", "セキュリティ", "権限制御", "画面・機能の権限制御が定義されているか？", "Critical", ("権限", "認可", "ロール")),
        Viewpoint("a11y", "アクセシビリティ", "アクセシビリティ", "アクセシビリティ要件が定義されているか？", "Medium", ("アクセシビリティ", "代替テキスト", "コントラスト")),
    ),
    "detail": (
        Viewpoint("overview", "完全性", "処理概要", "処理概要が記述されているか？", "Medium", ("処理概要", "機能概要")),
        Viewpoint("input", "完全性", "入力", "処理の入力が定義されているか？", "High", ("入力",)),
        Viewpoint("output", "出力", "出力", "処理の出力が定義されているか？", "High", ("出力",)),
        Viewpoint("precondition", "完全性", "前提条件", "処理の前提条件が定義されているか？", "Medium", ("前提条件", "事前条件")),
        Viewpoint("postcondition", "完全性", "事後条件", "処理の事後条件が定義されているか？", "Medium", ("事後条件",)),
        Viewpoint("flow", "完全性", "処理フロー", "処理フローが記述されているか？", "High", ("処理フロー", "フローチャート")),
        Viewpoint("branch", "正確性", "分岐条件", "分岐条件が漏れなく定義されているか？", "High", ("分岐", "条件分岐")),
        Viewpoint("db-access", "DB", "DBアクセス", "DBアクセスの対象と方式が定義されているか？", "High", ("DBアクセス", "テーブルアクセス")),
        Viewpoint("sql", "DB", "SQL", "発行するSQLが定義されているか？", "Medium", ("SQL",)),
        Viewpoint("transaction", "トランザクション", "トランザクション", "トランザクション境界が定義されているか？", "High", ("トランザクション", "コミット")),
        Viewpoint("lock", "排他", "排他制御", "排他制御方式が定義されているか？", "High", ("排他", "ロック")),
        Viewpoint("error", "エラー処理", "エラー処理", "エラー処理が定義されているか？", "High", ("エラー処理", "異常時")),
        Viewpoint("exception", "例外処理", "例外処理", "例外処理が定義されているか？", "High", ("例外処理", "例外時")),
        Viewpoint("log", "ログ", "ログ", "ログ出力の内容とレベルが定義されているか？", "Medium", ("ログ",)),
        Viewpoint("external-if", "IF", "外部IF", "外部インタフェースの仕様が定義されているか？", "High", ("外部IF", "インタフェース", "連携")),
        Viewpoint("retry", "性能", "リトライ", "リトライ方針が定義されているか？", "High", ("リトライ", "再試行")),
        Viewpoint("timeout", "性能", "タイムアウト", "タイムアウト値が定義されているか？", "High", ("タイムアウト",)),
        Viewpoint("security", "セキュリティ", "セキュリティ", "セキュリティ要件が定義されているか？", "Critical", ("セキュリティ", "認証", "認可", "暗号")),
        Viewpoint("performance", "性能", "性能", "性能要件が定義されているか？", "Medium", ("性能", "レスポンス", "スループット")),
    ),
    "database": (
        Viewpoint("naming", "命名", "命名規則", "テーブル・カラムの命名規則が定義されているか？", "Medium", ("命名", "物理名", "論理名")),
        Viewpoint("pk", "DB", "主キー", "主キーの定義方針が示されているか？", "High", ("主キー", "プライマリキー")),
        Viewpoint("fk", "DB", "外部キー", "外部キー制約の方針が示されているか？", "High", ("外部キー", "参照整合")),
        Viewpoint("index", "DB", "インデックス", "インデックスの設計方針が示されているか？", "Medium", ("インデックス",)),
        Viewpoint("datatype", "DB", "データ型", "カラムのデータ型と桁の方針が示されているか？", "High", ("データ型", "桁")),
        Viewpoint("null", "DB", "NULL", "NULL許可の方針が示されているか？", "Medium", ("NULL", "ヌル")),
        Viewpoint("transaction", "トランザクション", "トランザクション", "トランザクション方針が示されているか？", "High", ("トランザクション",)),
        Viewpoint("lock", "排他", "排他制御", "排他制御方式が示されているか？", "High", ("排他", "ロック")),
        Viewpoint("history", "保守性", "履歴", "更新履歴・監査項目の方針が示されているか？", "Medium", ("履歴", "登録日時", "更新日時")),
        Viewpoint("delete", "DB", "削除", "論理削除・物理削除の方針が示されているか？", "Medium", ("論理削除", "物理削除")),
        Viewpoint("encryption", "セキュリティ", "暗号化", "機微情報の暗号化方針が示されているか？", "Critical", ("暗号", "機微", "個人情報")),
        Viewpoint("archive", "保守性", "アーカイブ", "データ保持期間・アーカイブ方針が示されているか？", "Low", ("保持期間", "アーカイブ", "退避")),
    ),
    "api": (
        Viewpoint("endpoint", "API", "エンドポイント", "エンドポイントの命名規則が定義されているか？", "Medium", ("エンドポイント", "URI", "パス")),
        Viewpoint("method", "API", "HTTPメソッド", "HTTPメソッドの使い分けが定義されているか？", "Medium", ("メソッド", "GET", "POST")),
        Viewpoint("request", "API", "リクエスト", "リクエスト仕様が定義されているか？", "High", ("リクエスト",)),
        Viewpoint("response", "API", "レスポンス", "レスポンス仕様が定義されているか？", "High", ("レスポンス",)),
        Viewpoint("status", "API", "ステータスコード", "ステータスコードの使い分けが定義されているか？", "High", ("ステータスコード", "HTTPステータス")),
        Viewpoint("error", "エラー処理", "エラー応答", "エラー応答の形式が定義されているか？", "High", ("エラー応答", "エラー形式", "エラーコード")),
        Viewpoint("auth", "セキュリティ", "認証・認可", "APIの認証・認可方式が定義されているか？", "Critical", ("認証", "認可", "トークン")),
        Viewpoint("version", "保守性", "バージョニング", "APIのバージョニング方針が定義されているか？", "Medium", ("バージョ",)),
        Viewpoint("idempotency", "正確性", "冪等性", "冪等性の要否が定義されているか？", "High", ("冪等", "リトライ")),
        Viewpoint("timeout", "性能", "タイムアウト", "タイムアウト値が定義されているか？", "High", ("タイムアウト",)),
        Viewpoint("ratelimit", "性能", "流量制御", "流量制御・上限件数が定義されているか？", "Medium", ("流量", "レート", "上限")),
    ),
    "batch": (
        Viewpoint("trigger", "バッチ", "起動条件", "バッチの起動条件が定義されているか？", "High", ("起動", "スケジュール", "トリガ")),
        Viewpoint("io", "バッチ", "入出力", "入力ファイル・出力ファイルが定義されているか？", "High", ("入力ファイル", "出力ファイル")),
        Viewpoint("commit", "トランザクション", "コミット単位", "コミット単位が定義されているか？", "High", ("コミット", "中間コミット")),
        Viewpoint("rerun", "バッチ", "リラン", "異常終了時のリラン方針が定義されているか？", "High", ("リラン", "再実行", "再処理")),
        Viewpoint("multiplex", "排他", "多重起動", "多重起動の抑止方針が定義されているか？", "High", ("多重起動", "排他")),
        Viewpoint("log", "ログ", "処理件数", "処理件数のログ出力が定義されているか？", "Medium", ("処理件数", "件数ログ")),
        Viewpoint("window", "性能", "処理時間", "処理時間・実行時間帯の制約が定義されているか？", "Medium", ("処理時間", "実行時間", "時間帯")),
    ),
    "security": (
        Viewpoint("authn", "セキュリティ", "認証", "認証方式が定義されているか？", "Critical", ("認証",)),
        Viewpoint("authz", "セキュリティ", "認可", "認可・権限設計が定義されているか？", "Critical", ("認可", "権限")),
        Viewpoint("crypto", "セキュリティ", "暗号化", "暗号化の対象と方式が定義されているか？", "Critical", ("暗号",)),
        Viewpoint("session", "セキュリティ", "セッション", "セッション管理が定義されているか？", "High", ("セッション",)),
        Viewpoint("audit", "ログ", "監査ログ", "監査ログの取得が定義されているか？", "High", ("監査", "アクセスログ")),
        Viewpoint("injection", "セキュリティ", "インジェクション", "インジェクション対策が定義されているか？", "Critical", ("インジェクション", "SQL", "XSS", "エスケープ")),
        Viewpoint("secret", "セキュリティ", "機密情報", "パスワード・鍵の取り扱いが定義されているか？", "Critical", ("パスワード", "秘密鍵", "クレデンシャル")),
    ),
}

#: 種別固有の観点が無い文書には、どの設計にも共通する観点を当てる
GENERIC_VIEWPOINTS: tuple[Viewpoint, ...] = (
    Viewpoint("naming", "命名", "命名規則", "命名規則が定義されているか？", "Medium", ("命名", "名称")),
    Viewpoint("error", "エラー処理", "エラー処理", "エラー処理の方針が定義されているか？", "High", ("エラー", "異常")),
    Viewpoint("log", "ログ", "ログ", "ログ出力の方針が定義されているか？", "Medium", ("ログ",)),
    Viewpoint("security", "セキュリティ", "セキュリティ", "セキュリティ要件が定義されているか？", "Critical", ("セキュリティ", "認証", "認可")),
    Viewpoint("traceability", "トレーサビリティ", "トレーサビリティ", "上流成果物との対応関係が定義されているか？", "Medium", ("トレーサビリティ", "対応表", "追跡")),
)


def viewpoints_for(document_type: str) -> tuple[Viewpoint, ...]:
    return VIEWPOINTS.get(document_type, GENERIC_VIEWPOINTS)
