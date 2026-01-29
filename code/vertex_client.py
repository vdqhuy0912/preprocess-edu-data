"""Vertex AI Client for Gemini 2.5 Flash.

Module quản lý kết nối và gọi Vertex AI với service account authentication.
"""

import os
import json
import time
from typing import Any
from google import genai
from google.genai import types


def get_client(key_path: str = None) -> genai.Client:
    """
    Khởi tạo Gemini client với Vertex AI backend.
    
    Args:
        key_path: Đường dẫn đến file service account JSON.
                  Default: key/uet-education-qa-data-for-sft-e1a2fc9a3a71.json
    
    Returns:
        genai.Client instance configured for Vertex AI
    """
    if key_path is None:
        key_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "key",
            "uet-education-qa-data-for-sft-e1a2fc9a3a71.json"
        )
    
    # Load service account để lấy project_id
    with open(key_path, "r", encoding="utf-8") as f:
        service_account = json.load(f)
    
    project_id = service_account["project_id"]
    
    # Set credentials environment variable
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
    
    # Initialize client with Vertex AI backend
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location="us-central1"
    )
    
    return client


def generate_with_retry(
    client: genai.Client,
    prompt: str,
    system_prompt: str = None,
    response_schema: dict = None,
    model_name: str = "gemini-2.5-flash-lite",
    max_retries: int = 10,
    retry_delay: float = 3.0
) -> str:
    """
    Gọi Gemini với retry logic.
    
    Args:
        client: genai.Client instance
        prompt: User prompt
        system_prompt: System instruction
        response_schema: JSON schema cho structured output
        model_name: Tên model để sử dụng
        max_retries: Số lần retry tối đa
        retry_delay: Thời gian chờ giữa các lần retry (giây)
    
    Returns:
        Response text từ model
    """
    
    config = types.GenerateContentConfig(
        temperature=0.7,
        top_p=0.95,
        max_output_tokens=8192,
    )
    
    if system_prompt:
        config.system_instruction = system_prompt
    
    if response_schema:
        config.response_mime_type = "application/json"
        config.response_schema = response_schema
    
    contents = [prompt]
    
    current_delay = retry_delay
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            return response.text
        except Exception as e:
            error_str = str(e).lower()
            # Nếu là lỗi Rate Limit (429) hoặc Resource Exhausted
            if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
                wait_time = 60 if attempt < 3 else current_delay * 2
                print(f"\n[RATE LIMIT] Đã chạm giới hạn quota. Thử lại lần {attempt + 1}/{max_retries} sau {wait_time}s...")
                time.sleep(wait_time)
                current_delay = wait_time
            elif attempt < max_retries - 1:
                print(f"\n[ERROR] Lỗi không xác định: {e}. Thử lại sau {current_delay}s...")
                time.sleep(current_delay)
                current_delay *= 1.5 # Exponential backoff
            else:
                print(f"\n[FATAL] Đã thử {max_retries} lần nhưng vẫn thất bại cho dialog này.")
                raise


if __name__ == "__main__":
    # Test connection
    client = get_client()
    response = generate_with_retry(
        client,
        prompt="Xin chào, bạn là ai?",
        system_prompt="Bạn là trợ lý AI của trường đại học."
    )
    print(response)
