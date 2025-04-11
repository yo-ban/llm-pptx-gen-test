"""
アプリケーションの設定値、定数、ロギング設定を管理します。
"""
import logging
import os
from dotenv import load_dotenv

# --- 環境変数読み込み ---
load_dotenv()

# --- ロギング設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- PowerPoint テンプレート関連 ---
TEMPLATE_DIR = "templates"
TEMPLATE_FILE_PATH = os.path.join(TEMPLATE_DIR, "template.pptx")
DEFAULT_TEMPLATE_PATH = None # デフォルトテンプレートを使う場合は None

# --- レイアウトマッピング ---
# 使用するテンプレートファイルに応じて調整が必要
LAYOUT_MAPPING = {
    "title_slide": 0,
    "text_left_title": 1,
    "title_with_bg_image": 2,
    "text": 3,
    "section_header": 4,
    "two_column": 5,
    "two_column_right_wide": 6,
    "content_with_image_right": 7,
    "content_with_table_right": 8,
    "two_column_left_wide": 9,
    "table": 10,
    "text_large_left_title": 11,
    # "blank": 12, # 必要なら追加
}

LAYOUT_DESCRIPTION = {
    "title_slide": "プレゼンテーション全体のタイトルや、章の扉ページなど、大きな区切りに使用します。コンテンツ本文はありません。",
    "text_left_title": "左側に縦書きのタイトル、右側にコンテンツ（本文）を配置します。コンテンツエリアは比較的狭いため、キーメッセージと短い説明文などに適しています。",
    "title_with_bg_image": "スライドの背景に画像を表示し、その上にタイトルや短いテキストを重ねます。視覚的なインパクトが重要な導入部や区切りに適しています。多くの本文を載せるのには向きません。",
    "text": "最も標準的なレイアウトです。上部にタイトル、下部にコンテンツ（箇条書き、段落など）を配置します。テキスト中心のページや、ある程度の量の情報を記述するのに最適です。",
    "section_header": "大きなセクションや章の開始を示すためのレイアウトです。上部にタイトル、下部にサブタイトル（または短い説明文）を配置します。本文コンテンツはありません。",
    "two_column": "コンテンツを左右均等な幅の2つのカラムに分けて表示します。2つの項目を比較したり、関連性の高い情報を並列で見せたりする場合に適しています。各カラムに入れられるテキスト量は中程度が望ましいです。",
    "two_column_right_wide": "2段組ですが、右側のカラムが左側よりも広くなっています。主に右側の情報を強調したい場合や、左側に補足情報、右側に主要情報を配置する場合に使用します。",
    "content_with_image_right": "左側に（タイトルと）コンテンツ、右側に画像を配置します。左側のコンテンツエリアは比較的狭いため、画像と関連する短い説明、少なめの箇条書きに適しています。テキスト量が多い内容には不向きです。",
    "content_with_table_right": "上部にタイトル、左側にコンテンツ、右側に表を配置します。左側のコンテンツエリアは狭いため、表に関連する補足説明や短い要約に適しています。テキスト量が多い内容には不向きです。",
    "two_column_left_wide": "2段組ですが、左側のカラムが右側よりも広くなっています。主に左側の情報を強調したい場合や、左側に主要情報、右側に補足情報を配置する場合に使用します。",
    "table": "上部にタイトル、下部に大きな表を配置するレイアウトです。表形式でデータを分かりやすく示すことに特化しています。表自体がスライドの主要なコンテンツとなります。",
    "text_large_left_title": "text_left_title に似ていますが、左側のタイトルエリアの文字サイズがより大きく、強調されています。",
    "title_with_blank": "上部にタイトルエリアのみがあり、既定のコンテンツエリアが存在しません。自由なshape配置が必要不可欠な場合に使用します。",
}

LAYOUT_HINT_TEXT = """
- **テキスト量が比較的多い場合:** `text` (標準レイアウト) を最優先で検討してください。次点で `two_column` 各種も可能ですが、1ページあたりの情報量は `text` より少なくなります。
- **画像や表をメインに見せたい場合:** それぞれ `image` や `table` に関連するレイアウトを選択しますが、付随するテキストが多くなる場合は、テキスト用のページを別途設けることを検討してください。
- **`content_with_image_right` や `content_with_table_right` は、付随テキストが少なくする必要があります。** 長文の箇条書きには適していません。
- 目的やコンテンツに合わせて、これらのレイアウトを効果的に組み合わせてください。
"""

PLACEHOLDER_SELECTION_HINT_TEXT = """
- テンプレートタイプが 'two_column' 系の場合は、左列を `content_placeholder_idx_main` に、右列を `content_placeholder_idx_secondary` に割り当ててください。
- テンプレートタイプが 'content_with_image_right' の場合は、左コンテンツを `content_placeholder_idx_main` に、右画像を `image_placeholder_idx_main` に割り当ててください。
- テンプレートタイプが 'content_with_table_right' の場合は、左コンテンツを `content_placeholder_idx_main` に、右表を `table_placeholder_idx_main` に割り当ててください。
- テンプレートタイプが 'title_with_bg_image' の場合は、背景に適したプレースホルダーを `background_image_placeholder_idx` に割り当ててください。
"""


DEFAULT_LAYOUT_INDEX = 3 # フォールバック用のレイアウトインデックス

# --- LLM 設定 ---
# MAIN_LLM_MODEL = "gemini-2.5-pro-exp-03-25"
MAIN_LLM_MODEL = "gemini-2.0-flash"
MAIN_LLM_TEMPERATURE = 0.2

PLACEHOLDER_SELECTOR_LLM_MODEL = "gpt-4o-mini"

VALIDATOR_LLM_MODEL = "gpt-4o-mini"

# --- 画像検索ツール関連 ---
DUMMY_IMAGE_DIR = "dummy_images"
DUMMY_CAT_IMAGE = os.path.join(DUMMY_IMAGE_DIR, "dummy_cat.jpg")
DUMMY_PYTHON_IMAGE = os.path.join(DUMMY_IMAGE_DIR, "dummy_python_logo.png")
DUMMY_PLACEHOLDER_IMAGE = os.path.join(DUMMY_IMAGE_DIR, "dummy_placeholder.png")

# --- 出力設定 ---
OUTPUT_DIR = "output"

