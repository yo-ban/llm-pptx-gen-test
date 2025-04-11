# ===== プロンプトテンプレート=====
VALIDATE_JSON_SYSTEM_PROMPT = """
あなたは与えられたJSON文字列を、指定されたPydanticモデルのJSONスキーマに従って修正・整形するアシスタントです。
元のJSONに含まれる情報を可能な限り維持しつつ、スキーマに準拠した有効なJSONオブジェクトのみを出力してください。
余計な説明や接頭辞（例: ```json）は含めないでください。
"""

VALIDATE_JSON_HUMAN_PROMPT_TEMPLATE = """
以下のJSON文字列を、下記のPydanticモデルのJSONスキーマに従って修正・整形し、有効なJSONオブジェクトとして出力してください。
元の情報の意味を変えずに、スキーマに準拠するように修正してください。フィールドが不足している場合は適切に補完してください（不明な場合はnullや空文字/リストを使用）。

対象のJSON文字列:
```json
{json_str}
```

期待されるPydanticモデルのJSONスキーマ:
```json
{schema_json}
```

修正・整形されたJSONオブジェクトのみを出力してください。
"""

# generate_page_content で使用するために定義

GENERATE_PAGE_CONTENT_SYSTEM_PROMPT = """
プレゼンテーション全体の情報及び本ページのアウトラインに基づいて、詳細コンテンツを指定形式で生成してください。
スライドサイズはワイド画面（16:9）です。
特に指示がない場合、アウトラインと同じ言語を使用してください。（アウトラインが英語なら英語、日本語なら日本語のスライドを作成）

# コンテンツ生成の重要事項： テキスト構造について
- あなたが生成する `content_blocks` (または `left_content_blocks`, `right_content_blocks`) は、PowerPointスライド上の**単一のテキストプレースホルダー**（テキストボックス）内に配置される内容全体を表します。
- 各 `ContentBlock` は、そのテキストプレースホルダー内での「見出し」とその「箇条書き群」の**1つのまとまり**を示します。
- `ContentBlock` の `heading` が**インデントレベル0**のテキストとなり、その下の `items` リスト内の各 `TextBlockItem` が**インデントレベル1以上**の箇条書きテキストになります。
- **複数の `ContentBlock` がリストになっている場合、それらは連続して1つのテキストプレースホルダー内に書き込まれます。** 各 `ContentBlock` が別々のテキストボックスになるわけではありません。
- 1つのテキストプレースホルダーに入れられるテキスト量には限りがあります。多すぎる場合は下記の対応が可能です。目安として、デフォルトのフォントサイズでは、11行前後でスライドの枠から逸脱します。
  - 各テキストのフォントサイズ(font_sizeの値)を調整する
  - `ContentBlock` の数を減らす
  - `ContentBlock` 内の `items` の数を調整する

# 利用可能なツール
{tools_description}
"""

GENERATE_PAGE_CONTENT_SYSTEM_PROMPT_NON_STRUCTURED_SUFFIX = """
# 応答形式
最終的な応答は必ず以下のJSONスキーマに準拠したJSONオブジェクトのみを```json ... ```ブロックで囲んで出力してください。

```json
{schema_json}
```
"""

GENERATE_PAGE_CONTENT_HUMAN_PROMPT_TEMPLATE = """
# プレゼンテーション全体タイトル
{presentation_title}

# プレゼンテーション全体概要
{presentation_summary}

# このページのアウトライン
{outline_json}
"""

OUTLINE_GENERATION_SYSTEM_PROMPT = """
ユーザーの要望に基づいて、プレゼンテーションのアウトラインをJSON形式で生成してください。

アウトラインには下記の情報を含めてください。
- `presentation_title` (プレゼンテーション全体のタイトル)
- `presentation_summary` (プレゼンテーション全体の概要)
- `pages` (各ページのアウトライン)

各ページのアウトラインには下記の情報を含めてください。
- `page_title` (そのページのタイトル)
- `page_summary` (そのページで説明する内容の概要)
- `plan` (前後のページを考慮したこのページのコンテンツ作成計画)
- `layout_type` (使用するレイアウトタイプ)

応答は必ず以下のJSONスキーマに準拠したJSONオブジェクトのみを```json ... ```ブロックで囲んで出力してください。
```json
{schema_json}
```

以下は利用可能な `layout_type` タイプとその説明です。各ページのコンテンツの内容、量、目的に応じて最適なものを選択してください。

{layout_descriptions_list}

**レイアウト選択のヒント:**
{layout_hint_text}
"""

OUTLINE_GENERATION_HUMAN_PROMPT = """
下記のユーザーの要望に基づいて、プレゼンテーションのアウトラインをJSON形式で生成してください。
特に指示がない場合、ユーザーの要望と同じ言語を使用してください。（要望が英語なら英語、日本語なら日本語）

ユーザーの要望:
{user_request}
"""


PLACEHOLDER_SELECTION_PROMPT = """
あなたはPowerPointスライドのレイアウトを決定するアシスタントです。
以下のスライド概要と、利用可能なプレースホルダーのリストが与えられます。

# スライド概要
{slide_outline_json}

# 利用可能なプレースホルダー (インデックス、名前、タイプを含む)
{available_placeholders_json}

このスライド概要の内容とテンプレートタイプ ({layout_type}) に基づいて、各要素（タイトル、サブタイトル、主要コンテンツ/左列、第2コンテンツ/右列、主要画像、第2画像、主要表、背景画像など）を配置するのに最も適切なプレースホルダーのインデックスを選択し、以下のJSONスキーマに準拠したJSONオブジェクトのみを```json ... ```ブロックで囲んで出力してください。要素に対応するプレースホルダーがない場合は `null` を指定してください。

```json
{schema_json}
```

要素に対応する適切なプレースホルダーがない場合は `null` を指定してください。
- タイトルは通常 'TITLE' タイプです。
- 主要コンテンツは 'BODY' または 'OBJECT' タイプです。
- 画像は 'PICTURE' または 'OBJECT' タイプです。
- 表は 'TABLE' または 'OBJECT' タイプです。
{placeholder_selection_hint_text}
"""
