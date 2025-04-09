"""
PowerPoint自動生成アプリケーションのエントリーポイント。
ユーザー入力を受け取り、Generatorを呼び出してプレゼンテーションを作成します。
"""
import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)
from typing import Dict, Any
from models import LLMConfig

# --- ローカルモジュールからのインポート ---
from config import (
    logger, TEMPLATE_FILE_PATH, DEFAULT_TEMPLATE_PATH,
    MAIN_LLM_MODEL, MAIN_LLM_TEMPERATURE,
    VALIDATOR_LLM_MODEL, OUTPUT_DIR, PLACEHOLDER_SELECTOR_LLM_MODEL
)
from generator import PowerPointGenerator

# ===== メイン実行ブロック =====
if __name__ == "__main__":
    logger.info("アプリケーション実行開始。")

    # --- LLM 初期化 ---
    llm_configs: Dict[str, LLMConfig] = {} # LLM設定を格納する辞書
    try:
        # --- メインLLMの設定 ---
        main_model_name = os.getenv("MAIN_LLM_MODEL", MAIN_LLM_MODEL)
        main_llm_instance = ChatGoogleGenerativeAI(
            model=main_model_name,
            temperature=MAIN_LLM_TEMPERATURE,
            max_retries=2,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.OFF,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.OFF,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.OFF,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.OFF,
                HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.OFF,
            },
        )
        llm_configs["main"] = LLMConfig(instance=main_llm_instance, supports_structured_output=False)
        logger.info(f"メインLLM ({main_model_name}) を初期化しました。構造化出力サポート: False")

        # --- Placeholder Selector LLMの設定 ---
        placeholder_selector_model_name = os.getenv("PLACEHOLDER_SELECTOR_LLM_MODEL", PLACEHOLDER_SELECTOR_LLM_MODEL)
        placeholder_selector_llm_instance = ChatOpenAI(
            model=placeholder_selector_model_name,
            temperature=0.0,
            max_retries=2
        )
        llm_configs["placeholder_selector"] = LLMConfig(instance=placeholder_selector_llm_instance, supports_structured_output=True)
        logger.info(f"Placeholder Selector LLM ({placeholder_selector_model_name}) を初期化しました。構造化出力サポート: True")

        # --- バリデーションLLMの設定 ---
        validator_model_name = os.getenv("VALIDATOR_LLM_MODEL", VALIDATOR_LLM_MODEL)
        validator_llm_instance = ChatOpenAI(
            model=validator_model_name,
            temperature=0.0,
            max_retries=2
        )
        # gpt-4o-mini も構造化出力をサポート
        llm_configs["validator"] = LLMConfig(instance=validator_llm_instance, supports_structured_output=True)
        logger.info(f"バリデーションLLM ({validator_model_name}) を初期化しました。構造化出力サポート: True")

    except Exception as e:
        logger.error(f"言語モデルの初期化に失敗しました: {e}")
        exit(1)

    # --- テンプレートパス決定 ---
    template_to_use = TEMPLATE_FILE_PATH if os.path.exists(TEMPLATE_FILE_PATH) else DEFAULT_TEMPLATE_PATH
    if template_to_use:
        logger.info(f"使用テンプレート: {template_to_use}")
    else:
        logger.info("デフォルトテンプレートを使用します。")

    # --- Generator インスタンス化 ---
    try:
        # 初期化時にLLM設定辞書を渡す
        generator = PowerPointGenerator(
            llm_configs=llm_configs,
            template_path=template_to_use
        )
    except Exception as e:
        logger.error(f"PowerPointGeneratorの初期化に失敗しました: {e}")
        exit(1)

    # --- ユーザー入力 (例) ---
    user_request = "サンプルスライド1枚"

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- プレゼンテーション生成実行 ---
    try:
        generator.create_presentation(user_request, output_dir=OUTPUT_DIR)
    except Exception as e:
        logger.exception("プレゼンテーション生成中に予期せぬエラーが発生しました。", exc_info=e)

    logger.info("アプリケーション実行完了。")

