"""
アプリケーションで使用する Pydantic モデルを定義します。
LLMとの構造化データのやり取りや、内部データ表現に使用されます。
"""
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any, Optional, Union, Literal, Annotated
from langgraph.graph import MessagesState
from langchain_core.language_models.chat_models import (
    BaseChatModel,
)

# --- アウトライン用 ---

class Page(BaseModel):
    """スライド1ページのアウトライン情報。"""
    page_title: str = Field(..., description="このページのスライドタイトル。")
    page_summary: str = Field(..., description="このページに含むコンテンツ概要")
    plan: str = Field(..., description="前後のページを考慮したこのページのコンテンツ作成計画")
    layout_type: Literal[
        "title_slide",
        "text",
        "text_left_title",
        "text_large_left_title",
        "image",
        "table",
        "section_header",
        "two_column",
        "two_column_right_wide",
        "two_column_left_wide",
        "content_with_image_right",
        "content_with_table_right",
        "title_with_bg_image",
        "title_with_blank", # 必要なら追加
    ] = Field(..., description="スライドのレイアウトタイプを指定")

class Outline(BaseModel):
    """プレゼンテーション全体のアウトライン構造。"""
    presentation_title: str = Field(..., description="プレゼンテーション全体のタイトル")
    presentation_summary: str = Field(..., description="プレゼンテーション全体の概要")
    pages: List[Page] = Field(..., description="プレゼンテーションの各ページのリスト")

# --- プレースホルダー選択結果用 ---

class PlaceholderSelection(BaseModel):
    """各要素を配置すべきプレースホルダーのインデックス情報。"""
    title_placeholder_idx: Optional[int] = Field(None, description="タイトル用")
    subtitle_placeholder_idx: Optional[int] = Field(None, description="サブタイトル用")
    content_placeholder_idx_main: Optional[int] = Field(None, description="主要コンテンツ用")
    content_placeholder_idx_secondary: Optional[int] = Field(None, description="第2コンテンツ用")
    image_placeholder_idx_main: Optional[int] = Field(None, description="主要画像用")
    image_placeholder_idx_secondary: Optional[int] = Field(None, description="第2画像用")
    table_placeholder_idx_main: Optional[int] = Field(None, description="主要表用")
    background_image_placeholder_idx: Optional[int] = Field(None, description="背景画像用 (通常インデックス不要)") # 背景はインデックス指定しないことが多い

# --- コンテンツ詳細用 ---

class TextBlockItem(BaseModel):
    """テキストの内容。インデントレベルやフォントサイズも指定可能。"""
    text: str = Field(..., description="テキストの内容")
    level: int = Field(..., description="インデントレベル (1から4)", ge=1, le=4)
    font_size: Optional[int] = Field(0, description="フォントサイズを指定可能。既定値: Level1=14, Level2=12, Level3=11, Level4=9", le=16)

class ContentBlock(BaseModel):
    """
    単一のテキストプレースホルダー内における「見出し（レベル0）」と「それに続く箇条書き（レベル1以上）」のまとまり。
    """
    heading: str = Field(..., description="このブロックの見出しとなるテキスト（インデントレベル0に相当）")
    font_size: Optional[int] = Field(0, description="見出しのフォントサイズを指定可能。既定値: 16", le=20)
    items: Optional[Annotated[list[TextBlockItem], Field(None, description="見出しに続く要素のリスト（レベル1以上）")]]

class TextPage(BaseModel):
    """テキスト主体のページ。"""
    header: str = Field(..., description="スライドタイトル")
    content_blocks: Annotated[list[ContentBlock], Field(..., max_length=5, description="主要テキストプレースホルダー内に配置される内容のリスト")]

class ImagePage(BaseModel):
    """画像を含むページ。"""
    header: str = Field(..., description="スライドタイトル")
    content_blocks: Annotated[list[ContentBlock], Field(..., description="主要テキストプレースホルダー内に配置される内容のリスト", max_length=3)]
    image_description: str = Field(..., description="画像の説明（検索/生成用）")
    image_path: str = Field(..., description="ツールによって取得された実際の画像ファイルパス")

class TablePage(BaseModel):
    """表を含むページ。"""
    header: str = Field(..., description="スライドタイトル")
    table_title: str = Field(..., description="表タイトル")
    table_data: List[List[str]] = Field(..., description="表データ(2Dリスト)")
    key_message: Optional[str] = Field("", description="キーメッセージ（任意）")

class SectionHeaderPage(BaseModel):
    """セクション見出しページ。"""
    header: str = Field(..., description="セクションタイトル")
    subtitle: str = Field(..., description="サブタイトル")

class TwoColumnPage(BaseModel):
    """2段組ページ。"""
    header: str = Field(..., description="スライドタイトル")
    left_content_blocks: Annotated[list[ContentBlock], Field(..., max_length=3, description="左カラムのテキストプレースホルダー内に配置される内容のリスト")]
    right_content_blocks: Annotated[list[ContentBlock], Field(..., max_length=3, description="右カラムのテキストプレースホルダー内に配置される内容のリスト")]

class ContentWithImageRightPage(BaseModel):
    """左コンテンツ＋右画像ページ。"""
    header: str = Field(..., description="スライドタイトル")
    left_content_blocks: Annotated[list[ContentBlock], Field(..., max_length=3, description="左カラムのテキストプレースホルダー内に配置される内容のリスト")]
    image_description: str = Field(..., description="画像の説明（検索/生成用）")
    image_path: str = Field(..., description="ツールによって取得された実際の画像ファイルパス")

class ContentWithTableRightPage(BaseModel):
    """左コンテンツ＋右表ページ。"""
    header: str = Field(..., description="スライドタイトル")
    left_content_blocks: Annotated[list[ContentBlock], Field(..., max_length=3, description="左カラムのテキストプレースホルダー内に配置される内容のリスト")]
    table_title: str = Field(..., description="表タイトル")
    table_data: List[List[str]] = Field(...)
    key_message: str = Field("", description="キーメッセージ（任意）")

class TitleWithBgImagePage(BaseModel):
    """背景画像付きタイトルページ。"""
    header: str = Field(..., description="スライドタイトル")
    subtitle: Optional[str] = Field(None, description="サブタイトル（任意）")
    image_description: str = Field(..., description="画像の説明（検索/生成用）")
    image_path: str = Field(..., description="ツールによって取得された実際の画像ファイルパス")

class TitlePage(BaseModel):
    """プレゼンテーションのタイトルページ。"""
    title: str = Field(..., description="プレゼンテーションタイトル")
    subtitle: Optional[str] = Field(None, description="サブタイトル（任意）")

# --- 全体コンテンツ用 Union ---
PageContent = Union[
    TextPage, ImagePage, TablePage, SectionHeaderPage, TwoColumnPage,
    ContentWithImageRightPage, ContentWithTableRightPage, TitleWithBgImagePage, TitlePage
]

class PowerPointContent(BaseModel):
    """プレゼンテーション全体の詳細コンテンツ。"""
    title: str = Field(..., description="プレゼンテーションタイトル")
    pages: List[PageContent] = Field(..., description="各ページの詳細コンテンツリスト")


# ===== LangGraph State =====
class AgentState(MessagesState):
    """LangGraphエージェントの状態"""
    # 既存のフィールド
    outline: Optional[Outline] = None
    page_selections: List[Optional[PlaceholderSelection]] = []
    page_contents: List[Optional[PageContent]] = [] # これは最終的には使われなくなるかも
    current_page_index: int = 0
    final_path: Optional[str] = None
    validated_content: Optional[Any] = None
    validation_error: Optional[str] = None

# ===== LLM 設定クラス =====
class LLMConfig(BaseModel):
    instance: BaseChatModel
    supports_structured_output: bool = True
