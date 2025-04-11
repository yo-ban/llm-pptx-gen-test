"""
LangChain および LangGraph に関連する定義と関数。
ツール定義、AgentState、Workflow生成関数など。
"""
import os
import re
import json
import logging
import functools  # partial を使うためにインポート
from typing import List, Optional, Union, Type, Tuple, Any
from pydantic import BaseModel, ValidationError
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import (
    BaseChatModel,
)
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from models import (
    PageContent, AgentState
)
from prompt_template import (
    VALIDATE_JSON_SYSTEM_PROMPT, VALIDATE_JSON_HUMAN_PROMPT_TEMPLATE
)
# config.py から定数をインポート
from config import (
    DUMMY_IMAGE_DIR, DUMMY_CAT_IMAGE, DUMMY_PYTHON_IMAGE, DUMMY_PLACEHOLDER_IMAGE
)

logger = logging.getLogger(__name__)


# ===== ツール定義 =====
@tool
def search_similar_image(query: str) -> str:
    """
    スライドに画像が必要な場合に、クエリに最も近い画像ファイルのパスを検索して返します。

    Args:
        query (str): 画像検索クエリ。

    Returns:
        str: 画像ファイルのパス。
    """
    logger.info(f"画像検索クエリ: '{query}'")
    os.makedirs(DUMMY_IMAGE_DIR, exist_ok=True)
    for p in [DUMMY_CAT_IMAGE, DUMMY_PYTHON_IMAGE, DUMMY_PLACEHOLDER_IMAGE]:
        if not os.path.exists(p):
            try:
                with open(p, 'w') as f:
                    pass
                logger.info(f"ダミー画像ファイルを作成: {p}")
            except OSError as e:
                logger.error(f"ダミー画像作成失敗: {p}, Error: {e}")
                return DUMMY_PLACEHOLDER_IMAGE

    if "cat" in query.lower():
        return DUMMY_CAT_IMAGE
    elif "python" in query.lower():
        return DUMMY_PYTHON_IMAGE
    else:
        return DUMMY_PLACEHOLDER_IMAGE

# ===== 構造化出力のバリデーションと再パース =====
def extract_json_from_text(text: str) -> Optional[str]:
    """テキストから ```json ... ``` ブロック内のJSON文字列を抽出する"""
    match = re.search(r"```json\s*({.*?})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    # JSONが裸で返ってくる場合も考慮 (簡易的なチェック)
    if text.strip().startswith("{") and text.strip().endswith("}"):
        return text.strip()
    return None

def validate_and_parse_json(
    raw_output: Union[str, BaseMessage],
    expected_class: Type[BaseModel],
    validator_llm: BaseChatModel,
    max_attempts: int = 2  # 再パース試行回数
) -> Optional[BaseModel]:
    """
    LLMの出力を指定されたPydanticモデルにパースする。失敗した場合、バリデーションLLMで修正を試みる。

    Args:
        raw_output (Union[str, BaseMessage]): LLMからの生の出力（文字列 or メッセージオブジェクト）。
        expected_class (Type[BaseModel]): 期待するPydanticモデルクラス。
        validator_llm (ChatOpenAI): 修正・バリデーションに使用するLLM。
        max_attempts (int): バリデーションLLMによる修正試行の最大回数。

    Returns:
        Optional[BaseModel]: パース/修正されたPydanticモデルインスタンス、または失敗した場合はNone。
    """
    if isinstance(raw_output, BaseMessage):
        content = getattr(raw_output, 'content', '')
        if not content and hasattr(raw_output, 'text'):  # ToolMessage など
            content = getattr(raw_output, 'text', '')
    else:
        content = str(raw_output)

    if not content:
        logger.warning(f"入力コンテンツが空です。パースできません ({expected_class.__name__})。")
        return None

    logger.debug(
        f"パース試行 ({expected_class.__name__}): Input='{content[:100]}...'")

    # 1. 直接 model_validate_json を試す (```json タグを除去)
    json_str_cleaned = content.replace(
        "```json", "").replace("```", "").strip()
    try:
        # 空文字の場合 ValueError を起こすのでチェック
        if json_str_cleaned:
            validated_data = expected_class.model_validate_json(
                json_str_cleaned)
            logger.info(f"直接パース成功 ({expected_class.__name__})")
            return validated_data
        else:
            logger.warning(
                f"クリーンナップ後のJSON文字列が空です ({expected_class.__name__})。")
    except ValidationError as ve:
        logger.warning(f"直接パース失敗 ({expected_class.__name__}): {ve}")
    except Exception as e:  # JSONDecodeError なども捕捉
        logger.warning(f"直接パース中に予期せぬエラー ({expected_class.__name__}): {e}")

    # 2. ```json ... ``` ブロックの抽出を試みる
    extracted_json = extract_json_from_text(content)
    if extracted_json:
        logger.debug(f"抽出されたJSON文字列で再試行 ({expected_class.__name__}).")
        try:
            validated_data = expected_class.model_validate_json(extracted_json)
            logger.info(f"抽出後JSONの直接パース成功 ({expected_class.__name__})")
            return validated_data
        except ValidationError as ve:
            logger.warning(
                f"抽出後JSONの直接パース失敗 ({expected_class.__name__}): {ve}")
        except Exception as e:
            logger.warning(
                f"抽出後JSONの直接パース中に予期せぬエラー ({expected_class.__name__}): {e}")
    else:
        logger.warning("JSONブロックが見つかりませんでした。元のcontentを使用します。")
        # JSONブロックが見つからなくても、元の content を使ってバリデーションLLMに投げる

    # 3. バリデーションLLMによる修正を試みる
    current_json_str = extracted_json or json_str_cleaned  # 抽出できればそれを、ダメなら元のを
    if not current_json_str:
        logger.error(
            f"バリデーションLLMに渡すJSON文字列がありません ({expected_class.__name__})。")
        return None

    for attempt in range(max_attempts):
        logger.info(
            f"バリデーションLLMによる修正試行 {attempt + 1}/{max_attempts} ({expected_class.__name__})...")
        try:
            prompt = ChatPromptTemplate.from_template(
                VALIDATE_JSON_HUMAN_PROMPT_TEMPLATE)
            schema_json = json.dumps(
                expected_class.model_json_schema(), indent=2, ensure_ascii=False)
            messages = [
                SystemMessage(content=VALIDATE_JSON_SYSTEM_PROMPT),
                HumanMessage(content=prompt.format(
                    json_str=current_json_str,
                    schema_json=schema_json
                ))
            ]
            # バリデーションLLMは構造化出力が安定している前提
            validator_model_with_parser = validator_llm.with_structured_output(
                expected_class)
            validated_response = validator_model_with_parser.invoke(messages)

            # invoke が成功すれば、期待する型のインスタンスが返るはず
            if isinstance(validated_response, expected_class):
                logger.info(
                    f"バリデーションLLMによる修正・パース成功 ({expected_class.__name__})")
                return validated_response
            else:
                # 通常ありえないが念のためログ
                logger.error(
                    f"バリデーションLLMが期待しない型を返しました: {type(validated_response)}")
                # 念のため、返ってきたオブジェクトを再検証してみる
                try:
                    validated_data = expected_class.model_validate(
                        validated_response)
                    logger.info(
                        f"バリデーションLLMの応答を再検証して成功 ({expected_class.__name__})")
                    return validated_data
                except Exception as final_validation_e:
                    logger.error(
                        f"バリデーションLLMの応答の最終検証に失敗 ({expected_class.__name__}): {final_validation_e}")
                    # 次の試行のために、文字列として取得を試みる
                    current_json_str = str(
                        validated_response) if validated_response else ""

        except Exception as e:
            logger.error(
                f"バリデーションLLM実行/パース中にエラー ({expected_class.__name__}) Attempt {attempt + 1}: {e}")
            # エラーが発生した場合、次の試行は行わない（無限ループ防止）
            break

    logger.error(f"全てのパース/修正試行に失敗しました ({expected_class.__name__})。")
    return None


# ===== LangGraph Workflow Creation =====
def create_content_gen_workflow(
    llm: BaseChatModel,
    validator_llm: BaseChatModel,  # バリデーション用LLMを受け取る
    tools: list,
    response_class: Type[PageContent],
    structured_output_supported: bool
) -> CompiledStateGraph:
    """
    特定のページコンテンツ生成用 LangGraph ワークフローを作成します。
    最終応答の検証ステップを含みます。

    Args:
        llm: コンテンツ生成に使用する言語モデル。
        validator_llm: 最終応答の検証/修正に使用するLLM (構造化出力サポート前提)。
        tools (list): 利用可能なツールのリスト。
        response_class (Type[PageContent]): 期待する出力Pydanticモデル。
        structured_output_supported (bool): llmが構造化出力をネイティブサポートするかどうか。

    Returns:
        CompiledStateGraph: コンパイル済みワークフロー。
    """
    # --- 画像検索ツールを強制する Runnable を準備 ---
    # search_similar_image ツールオブジェクトを取得 (tools リスト内にある前提)
    image_search_tool = next((t for t in tools if t.name == "search_similar_image"), None)
    if not image_search_tool:
        logger.warning("Workflow creation: search_similar_image tool not found in the provided tools list.")
        # 画像検索ツールがない場合は強制できないので、通常のLLMを使う
        forced_image_search_llm = None
    else:
        # search_similar_image のみを強制する LLM Runnable
        forced_image_search_llm = llm.bind_tools([image_search_tool], tool_choice="search_similar_image")

    # --- モデル設定 (構造化出力サポート有無に基づく) ---
    if structured_output_supported:
        logger.info(f"Creating workflow for {response_class.__name__} with structured output support.")
        # model_runnable = llm.bind_tools(tools + [response_class])
        model_runnable = llm.with_structured_output(response_class)

    else:
        logger.info(f"Creating workflow for {response_class.__name__} WITHOUT structured output support.")
        # model_runnable = llm.bind_tools(tools)
        model_runnable = llm

    # --- ノード定義 ---
    def call_model(state: AgentState):
        """LLMを呼び出すノード。画像レイアウトの場合は画像検索を優先試行。"""

        # リトライカウントを取得し、インクリメント
        current_retry_count = state.get("llm_call_retry_count", 0)
        logger.debug(f"Entering call_model for {response_class.__name__}. Attempt {current_retry_count + 1}")
        # 次回の呼び出しのためにカウントをインクリメントしておく（この戻り値に含まれる）
        next_retry_count = current_retry_count + 1

        # response_class が画像関連のクラスかどうで判断
        is_image_layout = 'image_path' in response_class.model_fields
        logger.info(f"{response_class.__name__} has image_path field: {is_image_layout}")

        # 状態内に search_similar_image の ToolMessage が既にあるかチェック
        has_image_search_result = any(
            isinstance(msg, ToolMessage) and msg.name == "search_similar_image"
            for msg in state.get("messages", [])
        )

        response: Optional[AIMessage] = None # 型アノテーションを追加
        llm_to_use = model_runnable

        if is_image_layout and not has_image_search_result and forced_image_search_llm:
            logger.info(f"LangGraph: Attempting forced 'search_similar_image' for {response_class.__name__}")
            llm_to_use = forced_image_search_llm
        else:
            logger.info(f"LangGraph: Using standard model call for {response_class.__name__}")
            llm_to_use = model_runnable

        try:
            response = llm_to_use.invoke(state["messages"])

            # 強制検索を試みたが、期待するツールコールが生成されなかった場合のフォールバック
            if llm_to_use == forced_image_search_llm and (
                not response or not response.tool_calls or not any(tc["name"] == "search_similar_image" for tc in response.tool_calls)
                ):
                logger.warning(f"Forced image search for {response_class.__name__} did not generate the expected tool call. Falling back to standard model.")
                response = model_runnable.invoke(state["messages"]) # 通常モデルで再試行

            # 空レスポンスかどうかをチェック
            is_empty_response = not response or (not response.content and not response.tool_calls)
            if is_empty_response:
                logger.warning(f"LLM returned an empty response for {response_class.__name__}")
                # 空レスポンスの場合は messages は更新せず、リトライカウントのみ返す
                return {"llm_call_retry_count": next_retry_count}

        except Exception as e:
            logger.error(f"Error during LLM invocation in call_model for {response_class.__name__}: {e}", exc_info=True)
            # エラーの場合も messages は更新せず、リトライカウントのみ返す
            return {"llm_call_retry_count": next_retry_count}

        # 正常な応答が得られた場合は、メッセージを追加し、リトライカウントをリセットして返す
        return {"messages": [response], "llm_call_retry_count": 0}


    tool_node = ToolNode(tools)

    # functools.partial を使って validator_llm を固定引数として渡す
    def _validate_final_response_node_func(state: AgentState, validator_llm_for_node: BaseChatModel):
        """最終応答を検証/修正し、状態を更新するノード"""
        logger.debug(
            f"Validating final response for {response_class.__name__}")
        last_message = state["messages"][-1] if state["messages"] else None
        validated_data = None
        error_message = None

        if not last_message:
            error_message = "No messages found in state for validation."
            logger.error(error_message)
            return {"validated_content": None, "validation_error": error_message}

        # 最後のメッセージから検証対象のデータを抽出
        raw_data_source = None
        if structured_output_supported and last_message.tool_calls and \
            any(tc["name"] == response_class.__name__ for tc in last_message.tool_calls):
            # 構造化サポートありで、期待するツールコールがある場合
            logger.info(f"Processing structured output supported case with tool call.")
            # 複数のツールコールがある場合も考慮し、最初に見つかったものを対象とする
            expected_tc = next(
                (tc for tc in last_message.tool_calls if tc["name"] == response_class.__name__), None)
            if expected_tc:
                raw_data_source = json.dumps(
                    expected_tc["args"])  # 引数をJSON文字列として渡す
                logger.debug(
                    f"Source for validation: Tool call args ({response_class.__name__})")
            else:
                logger.warning(
                    "Expected tool call name found, but couldn't extract args.")
                raw_data_source = last_message.content  # フォールバックとして content を試す
                logger.debug(
                    "Source for validation: Message content (fallback from tool call)")

        elif not structured_output_supported or not last_message.tool_calls:
            # 構造化サポートなし、またはツールコールがない場合、メッセージ内容を試す
            logger.info(f"Processing non-structured output case with message content.")
            raw_data_source = last_message.content
            logger.debug("Source for validation: Message content")
        else:
            # 期待しないツールコールのみの場合など
            logger.warning(
                f"Unexpected tool calls, attempting validation on message content. Calls: {[tc['name'] for tc in last_message.tool_calls]}")
            raw_data_source = last_message.content

        if raw_data_source:
            validated_data = validate_and_parse_json(
                raw_data_source,
                response_class,
                validator_llm_for_node  # partialで固定されたLLMを使用
            )
            if not validated_data:
                error_message = f"Final validation/parsing failed for {response_class.__name__}"
                logger.error(error_message +
                            f" Source: {str(raw_data_source)[:100]}...")
        else:
            error_message = f"Could not determine data source in the last message for validation ({response_class.__name__})"
            logger.error(error_message)

        logger.info(f"Validated data: {validated_data}")

        # 状態を更新 (messages はそのまま、validated_content と error を更新)
        return {"validated_content": validated_data, "validation_error": error_message}

    # validator_llm を部分適用した検証関数を作成
    validate_final_response_node = functools.partial(
        _validate_final_response_node_func, validator_llm_for_node=validator_llm)

    # --- 条件分岐ロジック (should_continue) ---
    # 強制ツールコールが失敗した場合でも、通常の model_runnable が呼ばれ、その結果に基づいて遷移する。
    def should_continue(state: AgentState):
        """次にどのノードに進むかを決定する。空レスポンスやエラーの場合はリトライを試みる。"""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        retry_count = state.get("llm_call_retry_count", 0) # agentノードが更新したカウント
        max_retries = state.get("max_llm_retries", 2)

        # 最後のメッセージがない、AIMessageでない、または内容が空か、リトライカウントが 0 より大きい場合
        # (つまり、call_model が正常な応答を返さなかった場合)
        is_invalid_or_empty = not last_message or not isinstance(last_message, AIMessage) or (not last_message.content and not last_message.tool_calls)
        needs_retry = retry_count > 0 # call_model がリトライカウントを増やした場合

        if is_invalid_or_empty or needs_retry:
            logger.warning(f"should_continue ({response_class.__name__}): Last message is invalid/empty or retry is needed (Retry count: {retry_count}).")
            if retry_count < max_retries:
                logger.info(f"Attempting retry {retry_count + 1}/{max_retries} by returning to agent.")
                return "agent" # agent に戻して再実行
            else:
                logger.error(f"Max retries ({max_retries}) reached for {response_class.__name__}. Proceeding to validation (likely failing).")
                return "validate" # 最大リトライ回数を超えたら検証へ

        # 最後のメッセージが有効な場合 (リトライ不要)
        if not last_message.tool_calls:
            logger.info(f"LangGraph ({response_class.__name__}): No tool calls. Proceeding to validation.")
            return "validate"

        # ツールコールがある場合
        non_final_tool_calls = [
            tc for tc in last_message.tool_calls if tc["name"] != response_class.__name__
        ]

        if any(tc["name"] == "search_similar_image" for tc in non_final_tool_calls) or non_final_tool_calls:
            logger.info(f"LangGraph ({response_class.__name__}): Non-final tool call detected ({[tc['name'] for tc in non_final_tool_calls]}). Continuing to tools node.")
            return "continue"
        else:
            logger.info(f"LangGraph ({response_class.__name__}): Only final response tool call or unexpected calls found. Proceeding to validation. Calls: {[tc['name'] for tc in last_message.tool_calls]}")
            return "validate"

    # --- グラフ構築 ---
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("validator", validate_final_response_node)  # 検証ノードを追加
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",  # ツール実行が必要なら tools ノードへ
            "validate": "validator"  # ツール実行不要なら validator ノードへ
        }
    )
    workflow.add_edge("tools", "agent")  # ツール実行後は agent に戻る
    workflow.add_edge("validator", END)  # 検証後は終了

    logger.info(
        f"LangGraph workflow created for {response_class.__name__} (StructuredOutput: {structured_output_supported}) with validation step.")
    return workflow.compile()
