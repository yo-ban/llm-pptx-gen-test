# Slide Generation with Python

This project automatically generates PowerPoint presentations based on user requests using Python, `python-pptx`, and language models (like Gemini and OpenAI).

## Important Notes

*   **Verification Code:** This codebase is primarily intended for verification and demonstration purposes.
*   **Template Adjustments:** To use this effectively with your own presentations, you will need to adjust the layout mappings (`LAYOUT_MAPPING` in `config.py`) and potentially the placeholder selection logic (`select_placeholders` in `generator.py`) to match your specific PowerPoint slide master template.

## Features

*   Generates presentation outlines from user prompts.
*   Selects appropriate slide layouts based on content.
*   Generates slide content (text, images, tables) using LLMs.
*   Supports custom PowerPoint templates.
*   Uses LangChain and LangGraph for workflow management.

## Getting Started

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd slide-python
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Set up environment variables:**
    Create a `.env` file and add your API keys for the language models (e.g., `GOOGLE_API_KEY`, `OPENAI_API_KEY`).
4.  **Configure templates (Optional):**
    Place your custom `.pptx` template in the `templates/` directory and update `TEMPLATE_FILE_PATH` in `config.py`.
5.  **Run the main script:**
    ```bash
    python main.py
    ```

## Configuration

Key settings can be modified in `config.py`, including:

*   LLM models and parameters
*   Template paths
*   Layout mapping
*   Output directory

## Usage

Modify the `user_request` variable in `main.py` to specify the topic or content for your presentation.

```python
# --- User input (example) ---
user_request = "A presentation about the benefits of Python for data science."
```

The generated presentation will be saved in the `output/` directory.

## License

This project is licensed under the MIT License - see the [MIT License](LISCENSE) file for details. 