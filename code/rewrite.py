"""Rewrite conversations using Vertex AI Gemini 2.5 Flash.

Script tái cấu trúc ngữ nghĩa các conversation từ file Excel,
sử dụng Gemini để viết lại thành các cặp Q&A chất lượng cao.
"""

import os
import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm

# Add parent directory to path for imports
code_dir = os.path.dirname(__file__)
sys.path.insert(0, code_dir)

from vertex_client import get_client, generate_with_retry
from output_model import Message, Topic, QuestionType, ReasoningLevel


def safe_print(message: str):
    """Print với xử lý Unicode error cho Windows console."""
    try:
        print(message)
    except UnicodeEncodeError:
        # Fallback: encode sang ASCII và ignore các ký tự không hỗ trợ
        print(message.encode('ascii', 'ignore').decode('ascii'))


def load_system_prompt() -> str:
    """Load system prompt từ file."""
    prompt_path = Path(__file__).parent.parent / "prompt" / "PROMPT VIET LAI.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_response_schema() -> dict:
    """Build JSON schema cho structured output."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "dialog_id": {"type": "string"},
                "topic": {"type": "string", "enum": [e.value for e in Topic]},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["user", "assistant"]},
                            "content": {"type": "string"}
                        },
                        "required": ["role", "content"]
                    }
                },
                "multi_intent": {"type": "boolean"},
                "insufficient_context": {"type": "boolean"},
                "question_type": {"type": "string", "enum": [e.value for e in QuestionType]},
                "reasoning_level": {"type": "string", "enum": [e.value for e in ReasoningLevel]}
            },
            "required": ["dialog_id", "topic", "messages", "multi_intent", "insufficient_context", "question_type", "reasoning_level"]
        }
    }


def process_conversation(
    client,
    dialog_id: int,
    conversation: str,
    system_prompt: str,
    response_schema: dict,
    model_name: str
) -> list[dict]:
    """
    Xử lý một conversation và trả về danh sách Q&A pairs.
    """
    if pd.isna(conversation) or not str(conversation).strip():
        return []
    
    user_prompt = f"""## ĐOẠN HỘI THOẠI CẦN XỬ LÝ (Dialog ID: {dialog_id})

{conversation}

Hãy phân tích và viết lại đoạn hội thoại trên thành các cặp Q&A theo hướng dẫn."""

    try:
        response = generate_with_retry(
            client=client,
            prompt=user_prompt,
            system_prompt=system_prompt,
            response_schema=response_schema,
            model_name=model_name
        )
        
        # Validate response
        if not response or not response.strip():
            safe_print(f"Empty response for dialog {dialog_id}")
            return []
        
        # Parse JSON response
        qa_pairs = json.loads(response)
        
        # Validate parsed data
        if not isinstance(qa_pairs, list):
            safe_print(f"Invalid response format for dialog {dialog_id}: expected list, got {type(qa_pairs)}")
            return []
        
        # Thêm original_dialog_id vào mỗi pair
        for i, pair in enumerate(qa_pairs):
            pair["original_dialog_id"] = dialog_id
            # Update dialog_id với format chuẩn nếu chưa có
            if not pair.get("dialog_id") or pair["dialog_id"].startswith("dialog_id_"):
                pair["dialog_id"] = f"{dialog_id}_{i+1}"
        
        return qa_pairs
        
    except json.JSONDecodeError as e:
        safe_print(f"JSON parse error for dialog {dialog_id}: {e}")
        return []
    except Exception as e:
        safe_print(f"Error processing dialog {dialog_id}: {e}")
        return []


def save_results(all_results: list, output_path: Path):
    """Lưu kết quả vào file Excel và JSON."""
    if not all_results:
        return
    
    # Flatten messages for Excel output
    output_rows = []
    for qa in all_results:
        # Extract user and assistant messages
        user_msg = ""
        assistant_msg = ""
        for msg in qa.get("messages", []):
            if msg["role"] == "user":
                user_msg = msg["content"]
            elif msg["role"] == "assistant":
                assistant_msg = msg["content"]
        
        output_rows.append({
            "dialog_id": qa.get("dialog_id", ""),
            "original_dialog_id": qa.get("original_dialog_id", ""),
            "topic": qa.get("topic", ""),
            "question": user_msg,
            "answer": assistant_msg,
            "multi_intent": qa.get("multi_intent"),
            "insufficient_context": qa.get("insufficient_context"),
            "question_type": qa.get("question_type"),
            "reasoning_level": qa.get("reasoning_level"),
            "messages_json": json.dumps(qa.get("messages", []), ensure_ascii=False)
        })
    
    output_df = pd.DataFrame(output_rows)
    
    # Save to Excel
    output_df.to_excel(output_path, index=False)
    
    # Also save raw JSON
    json_path = output_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Tái cấu trúc ngữ nghĩa conversations sử dụng Gemini 2.5 Flash"
    )
    parser.add_argument(
        "--input",
        default="data/Full Message Final.xlsx",
        help="Đường dẫn file Excel input"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Đường dẫn file output"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số lượng rows xử lý"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Index bắt đầu xử lý"
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=100,
        help="Lưu checkpoint sau mỗi N rows (default: 100)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay giữa các request (giây, default: 0.5)"
    )
    parser.add_argument(
        "--key",
        default=None,
        help="Đường dẫn đến file service account JSON"
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash-lite",
        help="Tên model Vertex AI (default: gemini-2.5-flash-lite)"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    base_dir = Path(__file__).parent.parent
    input_path = base_dir / args.input
    
    if args.output:
        output_path = base_dir / args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = base_dir / "data" / f"restructured_{timestamp}.xlsx"
    
    # Load data
    safe_print(f"Loading data from {input_path}...")
    df = pd.read_excel(input_path)
    safe_print(f"Loaded {len(df)} rows")
    
    # Apply limits
    if args.limit:
        df = df.iloc[args.start:args.start + args.limit]
    elif args.start > 0:
        df = df.iloc[args.start:]
    
    # Initialize client
    safe_print(f"Initializing Vertex AI client (Model: {args.model})...")
    client = get_client(args.key)
    
    # Load prompt and schema
    system_prompt = load_system_prompt()
    response_schema = build_response_schema()
    
    # Process conversations
    all_results = []
    processed_count = 0
    
    safe_print("Processing conversations...")
    try:
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Rewriting"):
            dialog_id = row["Dialog ID"]
            conversation = row["Response of gemini"]
            
            qa_pairs = process_conversation(
                client=client,
                dialog_id=dialog_id,
                conversation=conversation,
                system_prompt=system_prompt,
                response_schema=response_schema,
                model_name=args.model
            )
            
            all_results.extend(qa_pairs)
            processed_count += 1
            
            # Throttling để tránh rate limit
            if args.delay > 0:
                time.sleep(args.delay)
            
            # Checkpoint: lưu kết quả định kỳ
            if processed_count % args.checkpoint_interval == 0:
                safe_print(f"\n[CHECKPOINT] Saving progress at {processed_count} dialogs...")
                save_results(all_results, output_path)
                
    except KeyboardInterrupt:
        safe_print("\n[INTERRUPTED] Saving progress before exit...")
    except Exception as e:
        safe_print(f"\n[ERROR] Unexpected error: {e}")
    finally:
        # Always save results
        if all_results:
            safe_print(f"\nFinalizing... Total Q&A pairs: {len(all_results)}")
            save_results(all_results, output_path)
            safe_print(f"Results saved to {output_path}")
            safe_print(f"JSON saved to {output_path.with_suffix('.json')}")
        else:
            safe_print("No results to save.")
    
    safe_print("Done!")


if __name__ == "__main__":
    main()

