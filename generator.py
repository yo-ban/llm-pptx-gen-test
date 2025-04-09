"""
PowerPointGenerator クラスを定義します。
プレゼンテーション生成の主要なロジックを担当します。
"""
import os
import json
from typing import List, Dict, Any, Optional, Union, Type
from pptx import Presentation
from pptx.util import Pt
from langchain_core.language_models.chat_models import (
    BaseChatModel,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool  # スキーマ生成用
from pydantic import BaseModel, ValidationError

# --- ローカルモジュールからのインポート ---
from config import logger, LAYOUT_MAPPING, DEFAULT_LAYOUT_INDEX
from models import (
    Outline, Page, PlaceholderSelection, PageContent,
    TextPage, ImagePage, TablePage, SectionHeaderPage, TwoColumnPage,
    ContentWithImageRightPage, ContentWithTableRightPage, TitleWithBgImagePage,
    LLMConfig
)
from pptx_utils import get_placeholder_details, add_sections_to_text_frame
from misc_utils import sanitize_filename
from langchain_utils import (
    search_similar_image, create_content_gen_workflow,
    validate_and_parse_json,
)
from prompt_template import (
    GENERATE_PAGE_CONTENT_SYSTEM_PROMPT, GENERATE_PAGE_CONTENT_HUMAN_PROMPT_TEMPLATE,
    GENERATE_PAGE_CONTENT_SYSTEM_PROMPT_NON_STRUCTURED_SUFFIX,
    OUTLINE_GENERATION_SYSTEM_PROMPT, PLACEHOLDER_SELECTION_PROMPT
)

class PowerPointGenerator:
    """
    PowerPointプレゼンテーション生成の全プロセスを管理するクラス。
    """

    def __init__(self, llm_configs: Dict[str, LLMConfig], template_path: Optional[str] = None):
        """
        初期化処理。LLM設定辞書、テンプレートパスなどを設定。
        """
        self.llm_configs = llm_configs
        # main と validator の存在チェック
        if "main" not in self.llm_configs or not self.llm_configs["main"].instance:
            raise ValueError("設定に 'main' LLM が必要です。")
        if "placeholder_selector" not in self.llm_configs or not self.llm_configs["placeholder_selector"].instance:
            raise ValueError("設定に 'placeholder_selector' LLM が必要です。")
        if "validator" not in self.llm_configs or not self.llm_configs["validator"].instance:
            raise ValueError("設定に 'validator' LLM が必要です。")

        self.main_llm_config: LLMConfig = self.llm_configs["main"]
        self.placeholder_selector_llm_config: LLMConfig = self.llm_configs["placeholder_selector"]
        self.validator_llm_config: LLMConfig = self.llm_configs["validator"]
        # バリデーションLLMは構造化出力をサポートしていることを強制（またはここでチェック）
        if not self.validator_llm_config.supports_structured_output:
            logger.warning("バリデーションLLMが構造化出力をサポートしていません。予期せぬ動作の可能性があります。")

        self.template_path = template_path
        self.tools = [search_similar_image]
        self.layout_mapping = LAYOUT_MAPPING
        self.default_layout_index = DEFAULT_LAYOUT_INDEX

        # --- 各ページタイプ用ワークフロー初期化 ---
        main_llm_instance = self.main_llm_config.instance
        validator_llm_instance = self.validator_llm_config.instance # バリデーションLLMも取得
        main_llm_structured_support = self.main_llm_config.supports_structured_output

        def _create_workflow(response_class):
            return create_content_gen_workflow(
                main_llm_instance,
                validator_llm_instance, # validator_llm を渡す
                self.tools if response_class != SectionHeaderPage else [],
                response_class,
                main_llm_structured_support
            )

        self.text_agent = _create_workflow(TextPage)
        self.image_agent = _create_workflow(ImagePage)
        self.table_agent = _create_workflow(TablePage)
        self.section_header_agent = _create_workflow(SectionHeaderPage)
        self.two_column_agent = _create_workflow(TwoColumnPage)
        self.content_with_image_right_agent = _create_workflow(ContentWithImageRightPage)
        self.content_with_table_right_agent = _create_workflow(ContentWithTableRightPage)
        self.title_with_bg_image_agent = _create_workflow(TitleWithBgImagePage)
        logger.info("PowerPointGenerator が初期化されました。")

    def _get_layout_index(self, template_type: str) -> int:
        """テンプレートタイプ名からレイアウトインデックスを取得。"""
        index = self.layout_mapping.get(
            template_type, self.default_layout_index)
        logger.info(f"テンプレートタイプ '{template_type}' -> レイアウトインデックス: {index}")
        return index

    def _invoke_structured_output_with_fallback(
        self,
        messages: List[BaseMessage],
        expected_class: Type[BaseModel],
        llm_config: LLMConfig
    ) -> Optional[BaseModel]:
        """
        構造化出力を試行し、失敗時にフォールバックを実行する内部メソッド。
        """
        llm_instance: BaseChatModel = llm_config.instance
        structured_supported: bool = llm_config.supports_structured_output

        try:
            if structured_supported:
                logger.info(f"Trying with_structured_output for {expected_class.__name__}")
                model_with_parser = llm_instance.with_structured_output(expected_class)
                response = model_with_parser.invoke(messages)
                if isinstance(response, expected_class):
                    logger.info(f"Direct structured output succeeded ({expected_class.__name__})")
                    return response
                else:
                    logger.warning(f"with_structured_output returned unexpected type: {type(response)}. Falling back.")
                    raw_output_content = getattr(response, 'content', str(response))
                    return validate_and_parse_json(raw_output_content, expected_class, self.validator_llm_config.instance)
            else:
                # 構造化出力非対応の場合、通常のinvokeを試行
                logger.info(f"Trying standard invoke for {expected_class.__name__} (non-structured support)")
                raw_response = llm_instance.invoke(messages)
                # 結果をバリデーションLLMでパース試行
                return validate_and_parse_json(raw_response, expected_class, self.validator_llm_config.instance)

        except Exception as e:
            logger.warning(f"Initial structured output attempt failed ({expected_class.__name__}): {e}. Falling back.")
            # 最初の試行でエラーが出た場合も、通常のinvokeを試みてパース
            try:
                logger.debug(f"Fallback: Trying standard invoke for {expected_class.__name__}")
                raw_response = llm_instance.invoke(messages)
                return validate_and_parse_json(raw_response, expected_class, self.validator_llm_config.instance)
            except Exception as inner_e:
                logger.error(f"Fallback invoke/parse failed ({expected_class.__name__}): {inner_e}")
                return None

    def generate_outline(self, user_input: str, chat_history: List = []) -> Optional[Outline]:
        """ユーザー入力からアウトラインを生成。"""
        logger.info("アウトライン生成を開始...")
        # スキーマを変数として定義
        schema_json_str = json.dumps(Outline.model_json_schema(), indent=2, ensure_ascii=False)
        logger.debug(f"アウトラインスキーマ: {schema_json_str}")

        outline_prompt = ChatPromptTemplate.from_messages([
            ("system", OUTLINE_GENERATION_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "以下の要望に基づいてアウトラインを作成してください:\n\n{input}")
        ])
        # format_messages に schema_json も渡す
        messages = outline_prompt.format_messages(
            input=user_input,
            chat_history=chat_history,
            schema_json=schema_json_str # スキーマ文字列を変数として渡す
        )

        # メインLLMの設定を使用してフォールバック付きで呼び出し
        outline = self._invoke_structured_output_with_fallback(
            messages, Outline, self.main_llm_config
        )

        if outline:
            logger.info("アウトライン生成完了。")
            logger.info(f"アウトライン: {json.dumps(outline.model_dump(), indent=2, ensure_ascii=False)}")
        else:
            logger.error("アウトライン生成に失敗しました。")
        return outline

    def select_placeholders(self, outline_page: Page, available_placeholders: List[Dict[str, Any]]) -> Optional[PlaceholderSelection]:
        """LLMでプレースホルダーを選択。"""
        logger.info(f"ページ '{outline_page.page_title}' のプレースホルダー選択を開始...")
        if not available_placeholders:
            logger.warning("利用可能なプレースホルダーがありません。選択スキップ。")
            # 空の選択を返す（後続処理でエラーにならないように）
            return PlaceholderSelection()

        # スキーマ、スライド概要、プレースホルダーリストを変数として定義
        schema_json_str = json.dumps(PlaceholderSelection.model_json_schema(), indent=2, ensure_ascii=False)
        slide_outline_json_str = outline_page.model_dump_json(indent=2)
        available_placeholders_json_str = json.dumps(available_placeholders, ensure_ascii=False)

        # ChatPromptTemplateではなくシンプルなPromptTemplateを使用しても良い
        prompt = PromptTemplate.from_template(PLACEHOLDER_SELECTION_PROMPT)

        # format に変数を渡す
        formatted_prompt = prompt.format(
            slide_outline_json=slide_outline_json_str,
            available_placeholders_json=available_placeholders_json_str,
            layout_type=outline_page.layout_type,
            schema_json=schema_json_str
        )
        messages = [HumanMessage(content=formatted_prompt)]

        # メインLLMの設定を使用してフォールバック付きで呼び出し
        selection = self._invoke_structured_output_with_fallback(
            messages, PlaceholderSelection, self.placeholder_selector_llm_config
        )

        if selection:
            logger.info(f"ページ '{outline_page.page_title}' のプレースホルダー選択完了。")
            logger.info(f"プレースホルダー選択: {selection.model_dump_json(indent=2)}")
        else:
            logger.error(f"ページ '{outline_page.page_title}' のプレースホルダー選択に失敗しました。")
            # 失敗した場合でも空のオブジェクトを返す（後続のエラーを防ぐため）
            selection = PlaceholderSelection()
        return selection

    def generate_page_content(self, presentation_title: str, presentation_summary: str, outline_page: Page) -> Optional[PageContent]:
        """ページのアウトラインから詳細コンテンツを生成。LangGraphワークフローの結果を取得・検証。"""
        logger.info(
            f"ページ '{outline_page.page_title}' ({outline_page.layout_type}) コンテンツ生成開始...")

        agent_map = {
            "text": (self.text_agent, TextPage), 
            "text_left_title": (self.text_agent, TextPage),
            "text_large_left_title": (self.text_agent, TextPage),
            "image": (self.image_agent, ImagePage), 
            "table": (self.table_agent, TablePage),
            "section_header": (self.section_header_agent, SectionHeaderPage),
            "two_column": (self.two_column_agent, TwoColumnPage),
            "two_column_right_wide": (self.two_column_agent, TwoColumnPage),
            "two_column_left_wide": (self.two_column_agent, TwoColumnPage),
            "content_with_image_right": (self.content_with_image_right_agent, ContentWithImageRightPage),
            "content_with_table_right": (self.content_with_table_right_agent, ContentWithTableRightPage),
            "title_with_bg_image": (self.title_with_bg_image_agent, TitleWithBgImagePage),
        }

        agent_to_invoke, expected_class = agent_map.get(
            outline_page.layout_type, (self.text_agent, TextPage))

        if outline_page.layout_type == "title_slide":
            logger.info(f"テンプレート '{outline_page.layout_type}' はコンテンツ生成スキップ。")
            return TextPage(header=outline_page.page_title, sections=[])

        # --- プロンプト準備 ---
        main_llm_structured_support = self.main_llm_config.supports_structured_output
        messages: List[BaseMessage] = []
        outline_json = outline_page.model_dump_json(indent=2)

        if main_llm_structured_support:
            # 構造化出力サポートモデル
            system_prompt = PromptTemplate.from_template(GENERATE_PAGE_CONTENT_SYSTEM_PROMPT)
            human_prompt = PromptTemplate.from_template(GENERATE_PAGE_CONTENT_HUMAN_PROMPT_TEMPLATE)
            messages = [
                SystemMessage(content=system_prompt.format(
                    tools_description=tools_description
                )),
                HumanMessage(content=human_prompt.format(
                    presentation_title=presentation_title,
                    presentation_summary=presentation_summary,
                    outline_json=outline_json
                ))
            ]
        else:
            # 構造化出力非サポートモデル
            schema_json = json.dumps(expected_class.model_json_schema(), indent=2, ensure_ascii=False)
            logger.info(f"schema_json: {schema_json}")
            current_tools = self.tools if expected_class != SectionHeaderPage else []
            tools_description = "なし"
            if current_tools:
                try:
                    tools_description = "\n".join([f"{t.name}: {t.description}" for t in current_tools])
                except Exception as e:
                    logger.error(f"Tool description generation failed: {e}")
                    tools_description = "[Error generating tool description]"
            
            system_prompt = PromptTemplate.from_template(
                GENERATE_PAGE_CONTENT_SYSTEM_PROMPT + GENERATE_PAGE_CONTENT_SYSTEM_PROMPT_NON_STRUCTURED_SUFFIX
            )
            human_prompt = PromptTemplate.from_template(GENERATE_PAGE_CONTENT_HUMAN_PROMPT_TEMPLATE)
            messages = [
                SystemMessage(content=system_prompt.format(
                    tools_description=tools_description,
                    schema_json=schema_json
                )),
                HumanMessage(content=human_prompt.format(
                    presentation_title=presentation_title,
                    presentation_summary=presentation_summary,
                    outline_json=outline_json
                ))
            ]


        # --- ワークフロー実行 ---
        if agent_to_invoke and expected_class:
            try:
                logger.debug(f"Invoking workflow for {expected_class.__name__}...")
                # ワークフローを実行し、最終状態を取得 (辞書として受け取る)
                response_state_dict = agent_to_invoke.invoke({"messages": messages})
                # ★デバッグログを追加して内容を確認
                logger.debug(f"Raw response state dict from workflow: {response_state_dict}")
                logger.debug(f"Type of raw response state dict: {type(response_state_dict)}")

                # AgentStateオブジェクトへの変換は行わず、辞書のままアクセスする
                if isinstance(response_state_dict, dict):
                    # .get() を使って安全に validated_content と validation_error を取得
                    validated_content = response_state_dict.get("validated_content")
                    validation_error = response_state_dict.get("validation_error")

                    # 取得した validated_content の型をチェック
                    if validated_content and isinstance(validated_content, expected_class):
                        logger.info(f"Page '{outline_page.page_title}' content generation and validation succeeded ({expected_class.__name__}).")
                        # ここでは Pydantic モデルインスタンスが取得できているはず
                        return validated_content
                    elif validated_content:
                        # 期待する型ではない場合のエラーログ
                        logger.error(f"Validation returned unexpected type. Expected {expected_class.__name__}, got {type(validated_content)}. Content: {str(validated_content)[:200]}...")
                        return None # 不正な型なので None を返す
                    else:
                        # 検証失敗時のログ (validation_error を使用)
                        last_msg_content = "N/A"
                        if response_state_dict.get("messages"):
                            try:
                                # response_state_dict から messages を取得
                                messages_list = response_state_dict.get("messages", [])
                                if messages_list:
                                    last_msg = messages_list[-1]
                                    last_msg_content = getattr(last_msg, 'content', str(last_msg))[:200] + "..."
                            except Exception as log_e:
                                logger.warning(f"Failed to get last message for logging: {log_e}")
                        logger.error(f"Page '{outline_page.page_title}' content validation failed. Error: {validation_error}. Last message content: {last_msg_content}")
                        return None # 検証失敗時はNoneを返す
                else:
                    # 予期せず辞書以外が返ってきた場合
                    logger.error(f"Workflow invoke returned unexpected type: {type(response_state_dict)}. Content: {str(response_state_dict)[:200]}...")
                    return None

            except Exception as e:
                logger.exception(
                    f"Error during content generation workflow execution or result processing ({expected_class.__name__}).", exc_info=e)
                return None
        else:
            logger.error(
                f"Page '{outline_page.page_title}' ({outline_page.layout_type}) - No agent/class found.")
            return None


    def populate_slide(self, slide, selection: PlaceholderSelection, content: PageContent):
        """生成されたコンテンツをスライドに配置。 image_path を使用。"""
        page_header = getattr(content, 'header', 'N/A')
        logger.info(f"Populating slide '{page_header}'...")

        try:
            # --- テキスト要素の配置 ---
            # 1. Title
            if selection.title_placeholder_idx is not None and hasattr(content, 'header'):
                try:
                    slide.placeholders[selection.title_placeholder_idx].text = content.header
                    logger.debug(f"  - Title -> Idx {selection.title_placeholder_idx}")
                except (IndexError, KeyError, AttributeError) as e: # KeyErrorも捕捉 (古いテンプレートなどでidxが存在しない場合)
                    logger.warning(f"  - Warn: Title Idx {selection.title_placeholder_idx} invalid or inaccessible: {e}")

            # 2. Subtitle
            if selection.subtitle_placeholder_idx is not None and hasattr(content, 'subtitle') and content.subtitle:
                try:
                    slide.placeholders[selection.subtitle_placeholder_idx].text = content.subtitle
                    logger.debug(f"  - Subtitle -> Idx {selection.subtitle_placeholder_idx}")
                except (IndexError, KeyError, AttributeError) as e:
                    logger.warning(f"  - Warn: Subtitle Idx {selection.subtitle_placeholder_idx} invalid or inaccessible: {e}")

            # 3. Main Content (Text)
            if selection.content_placeholder_idx_main is not None:
                sections = getattr(content, 'sections', getattr(content, 'left_sections', None))
                if sections:
                    try:
                        # Placeholderオブジェクトを取得
                        ph = slide.placeholders[selection.content_placeholder_idx_main]
                        if ph.has_text_frame:
                            add_sections_to_text_frame(ph.text_frame, sections)
                            logger.debug(f"  - Main Content -> Idx {selection.content_placeholder_idx_main}")
                        else:
                            logger.warning(f"  - Warn: Main Content Idx {selection.content_placeholder_idx_main} has no text frame.")
                    except (IndexError, KeyError, AttributeError) as e:
                        logger.warning(f"  - Warn: Main Content Idx {selection.content_placeholder_idx_main} invalid or inaccessible: {e}")

            # 4. Secondary Content (Text)
            if selection.content_placeholder_idx_secondary is not None:
                sections = getattr(content, 'right_sections', None)
                if sections:
                    try:
                        ph = slide.placeholders[selection.content_placeholder_idx_secondary]
                        if ph.has_text_frame:
                            add_sections_to_text_frame(ph.text_frame, sections)
                            logger.debug(f"  - Secondary Content -> Idx {selection.content_placeholder_idx_secondary}")
                        else:
                            logger.warning(f"  - Warn: Secondary Content Idx {selection.content_placeholder_idx_secondary} has no text frame.")
                    except (IndexError, KeyError, AttributeError) as e:
                        logger.warning(f"  - Warn: Secondary Content Idx {selection.content_placeholder_idx_secondary} invalid or inaccessible: {e}")

            # --- 非テキスト要素の配置 ---
            # 5. Main Image (image_path を使用)
            image_path = getattr(content, 'image_path', None)
            if selection.image_placeholder_idx_main is not None and image_path:
                if os.path.exists(image_path):
                    try:
                        ph = slide.placeholders[selection.image_placeholder_idx_main]
                        # プレースホルダーに挿入試行
                        ph.insert_picture(image_path)
                        logger.debug(f"  - Main Image -> Inserted into Idx {selection.image_placeholder_idx_main} ('{image_path}')")
                    except (IndexError, KeyError, AttributeError) as e:
                        logger.warning(f"  - Warn: Main Image Idx {selection.image_placeholder_idx_main} invalid or inaccessible: {e}. Adding as shape.")
                        # フォールバック: シェイプとして追加 (位置がずれる可能性)
                        try:
                            # プレースホルダーの位置情報を取得しようと試みる
                            ph_shape = slide.slide_layout.placeholders[selection.image_placeholder_idx_main]
                            slide.shapes.add_picture(image_path, ph_shape.left, ph_shape.top, width=ph_shape.width, height=ph_shape.height)
                            logger.debug(f"  - Fallback: Main Image added as shape ('{image_path}')")
                        except Exception as shape_e:
                            logger.error(f"  - Error adding picture as shape: {shape_e}")
                    except Exception as pic_e:
                        logger.error(f"  - Error inserting picture into placeholder Idx {selection.image_placeholder_idx_main}: {pic_e}")
                else:
                    logger.warning(f"  - Warn: Image file path does not exist: '{image_path}'")

            # 6. Main Table
            if selection.table_placeholder_idx_main is not None and hasattr(content, 'table_data'):
                table_data = content.table_data
                if table_data and isinstance(table_data, list) and len(table_data) > 0:
                    table_idx = selection.table_placeholder_idx_main
                    try:
                        # slide.placeholders を使用
                        ph = slide.placeholders[table_idx]
                        l, t, w, h = ph.left, ph.top, ph.width, ph.height
                        rows = len(table_data)
                        cols = len(table_data[0]) if rows > 0 else 0

                        if rows > 0 and cols > 0:
                            # 元のプレースホルダー削除処理
                            try:
                                ph_element = ph.element
                                ph_parent = ph_element.getparent()
                                if ph_parent is not None:
                                    ph_parent.remove(ph_element)
                                    logger.debug(f"  - Removed original placeholder at Idx {table_idx}")
                                else:
                                    logger.warning(f"  - Could not get parent of placeholder element at Idx {table_idx}. Skipping removal.")
                            except Exception as remove_e:
                                logger.warning(f"  - Failed to remove original placeholder at Idx {table_idx}: {remove_e}. Continuing...")

                            # テーブルを追加
                            shape = slide.shapes.add_table(rows, cols, l, t, w, h)
                            table = shape.table
                            for r, row in enumerate(table_data):
                                for c, cell_content in enumerate(row):
                                    cell = table.cell(r, c)
                                    cell.text = str(cell_content)
                                    if cell.text_frame:
                                        for paragraph in cell.text_frame.paragraphs:
                                            if paragraph.font:
                                                paragraph.font.size = Pt(16) # サイズ調整
                            logger.debug(f"  - Main Table -> Added at Idx {table_idx} position ({rows}x{cols})")
                        else:
                            logger.warning(f"  - Warn: Table data is invalid (rows={rows}, cols={cols}).")
                    # エラーハンドリングを少し詳細化
                    except (IndexError, KeyError) as e:
                        logger.warning(f"  - Warn: Main Table Idx {table_idx} not found in slide.placeholders: {e}")
                    except AttributeError as e:
                        logger.warning(f"  - Warn: Main Table Placeholder (Idx {table_idx}) is invalid or inaccessible: {e}")
                    except Exception as table_e:
                        logger.error(f"  - Error processing table at Idx {table_idx}: {table_e}", exc_info=True)

            # 7. Background Image (image_path を使用)
            bg_image_path = getattr(content, 'image_path', None) # TitleWithBgImagePage も image_path を持つ
            if selection.background_image_placeholder_idx is not None and bg_image_path:
                if os.path.exists(bg_image_path):
                    try:
                        slide.background.fill.solid() # 既存の背景をクリア
                        slide.background.fill.picture(bg_image_path)
                        logger.debug(f"  - Background Image set ('{bg_image_path}')")
                    except Exception as bg_e:
                        logger.error(f"  - Error setting background image: {bg_e}")
                else:
                    logger.warning(f"  - Warn: Background image file path does not exist: '{bg_image_path}'")

        except Exception as e:
            logger.exception(f"Error populating slide '{page_header}'.", exc_info=e)

        logger.info(f"Slide '{page_header}' population complete.")

    def create_presentation(self, user_input: str, output_dir: str):
        """プレゼンテーション生成のメインプロセスを実行。"""
        logger.info("プレゼンテーション生成プロセス開始。")
        # 1. アウトライン生成
        outline = self.generate_outline(user_input)
        if not outline or not outline.pages:
            logger.error("アウトライン生成失敗。処理中断。")
            return

        # 2. Presentationオブジェクト準備
        try:
            prs = Presentation(self.template_path) if self.template_path and os.path.exists(
                self.template_path) else Presentation()
            logger.info(
                f"Presentation オブジェクト準備完了 (Template: {self.template_path if self.template_path and os.path.exists(self.template_path) else 'Default'})")
        except Exception as e:
            logger.error(f"Presentation オブジェクト準備失敗: {e}")
            return

        all_page_selections = []
        all_page_contents = []

        presentation_title = outline.presentation_title
        presentation_summary = outline.presentation_summary

        # 3. 各ページ処理 (プレースホルダー選択 -> コンテンツ生成)
        total_pages = len(outline.pages)
        for i, page_outline in enumerate(outline.pages):
            logger.info(
                f"--- ページ {i+1}/{total_pages}: '{page_outline.page_title}' ({page_outline.layout_type}) 処理開始 ---")
            layout_index = self._get_layout_index(page_outline.layout_type)

            # プレースホルダー選択
            available_placeholders = get_placeholder_details(prs, layout_index)
            selection = self.select_placeholders(
                page_outline, available_placeholders)
            if selection is None:  # select_placeholders が None を返す可能性があるためチェック
                logger.warning(
                    f"ページ {i+1} プレースホルダー選択失敗。デフォルト値も設定できませんでした。スキップします。")
                all_page_selections.append(PlaceholderSelection())  # 空の選択を追加
                all_page_contents.append(None)  # コンテンツもスキップ
                continue
            all_page_selections.append(selection)

            # コンテンツ生成
            page_content = self.generate_page_content(presentation_title, presentation_summary, page_outline)
            if page_content is None:
                logger.warning(f"ページ {i+1} コンテンツ生成失敗。スキップ。")
            all_page_contents.append(page_content)  # 失敗しても None を追加
            logger.info(f"--- ページ {i+1}/{total_pages} 選択・生成完了 ---")

        # 4. スライド構築
        logger.info("スライド構築開始...")
        for i, page_outline in enumerate(outline.pages):
            logger.info(
                f"スライド {i+1}/{total_pages} ('{page_outline.page_title}') 構築中...")
            content = all_page_contents[i]
            selection = all_page_selections[i]

            if content is None:
                logger.warning(f"ページ {i+1} コンテンツ無しのためスライド構築スキップ。")
                continue
            # PlaceholderSelection がNoneでないことは上で保証されているはずだが念のため
            if selection is None:
                logger.warning(f"ページ {i+1} プレースホルダー選択データ無しのためスライド構築スキップ。")
                continue

            layout_index = self._get_layout_index(page_outline.layout_type)
            try:
                slide_layout = prs.slide_layouts[layout_index]
                slide = prs.slides.add_slide(slide_layout)
                self.populate_slide(slide, selection, content)
                logger.info(f"スライド {i+1}/{total_pages} 構築完了。")
            except IndexError:
                logger.error(
                    f"レイアウトインデックス {layout_index} が不正。スライド {i+1} スキップ。")
            except Exception as e:
                logger.error(
                    f"スライド {i+1} ('{page_outline.page_title}') 作成中に予期せぬエラー: {e}", exc_info=True)

        # 5. 保存
        try:
            sanitized_title = sanitize_filename(presentation_title)
            output_path = os.path.join(output_dir, f"{sanitized_title}.pptx")
            prs.save(output_path)
            logger.info(f"プレゼンテーションを '{output_path}' に保存完了。")
        except Exception as e:
            logger.error(f"保存エラー: {e}")

        logger.info("プレゼンテーション生成プロセス完了。")
