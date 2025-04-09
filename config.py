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
DEFAULT_LAYOUT_INDEX = 3 # フォールバック用のレイアウトインデックス

# --- LLM 設定 ---
MAIN_LLM_MODEL = "gemini-2.5-pro-exp-03-25"
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

