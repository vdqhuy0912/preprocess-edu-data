"""
Script để parse văn bản từ file .docx thành JSON chunks
phục vụ RAG. Bảng biểu được chuyển thành LaTeX tabular format.
"""

import re
import json
import sys
from pathlib import Path
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from typing import List, Dict, Any


def table_to_latex(table: Table) -> str:
    """Chuyển đổi bảng Word sang LaTeX tabular format."""
    if not table.rows:
        return ""
    
    # Xác định số cột
    num_cols = len(table.rows[0].cells)
    
    # Tạo header với alignment (centered cho tất cả cột)
    col_format = "|" + "c|" * num_cols
    latex_lines = [f"\\begin{{tabular}}{{{col_format}}}"]
    latex_lines.append("\\hline")
    
    # Xử lý từng hàng
    for row in table.rows:
        cells = []
        for cell in row.cells:
            # Lấy text từ cell, xử lý ký tự đặc biệt
            cell_text = cell.text.strip()
            # Escape các ký tự đặc biệt của LaTeX
            cell_text = cell_text.replace("&", "\\&")
            cell_text = cell_text.replace("%", "\\%")
            cell_text = cell_text.replace("$", "\\$")
            cell_text = cell_text.replace("#", "\\#")
            cell_text = cell_text.replace("_", "\\_")
            cell_text = cell_text.replace("{", "\\{")
            cell_text = cell_text.replace("}", "\\}")
            cell_text = cell_text.replace("~", "\\~")
            cell_text = cell_text.replace("^", "\\^")
            # Giữ newline trong cell
            cell_text = cell_text.replace("\n", "\n")
            cells.append(cell_text)
        
        # Nối các cell với &
        row_text = " & ".join(cells) + " \\\\\\\\"
        latex_lines.append(row_text)
        latex_lines.append("\\hline")
    
    latex_lines.append("\\end{tabular}")
    return "\n".join(latex_lines)


def create_chunks_for_rag(docx_path: str, chunk_size: int = 500) -> List[Dict[str, Any]]:
    """
    Parse file .docx và tạo chunks cho RAG.
    Mỗi chunk chứa text và metadata.
    """
    doc = Document(docx_path)
    chunks = []
    
    current_chunk = {
        "chunk_id": 0,
        "content": "",
        "tables": [],
        "metadata": {
            "source": str(docx_path),
            "type": "text"
        }
    }
    
    chunk_id = 0
    
    for element in doc.element.body:
        # Kiểm tra nếu là paragraph
        if element.tag.endswith('p'):
            para = Paragraph(element, doc)
            text = para.text.strip()
            
            if not text:
                continue
            
            # Thêm text vào chunk hiện tại
            if current_chunk["content"]:
                current_chunk["content"] += "\n" + text
            else:
                current_chunk["content"] = text
            
            # Nếu chunk đạt kích thước tối đa, lưu và tạo chunk mới
            if len(current_chunk["content"]) >= chunk_size:
                current_chunk["chunk_id"] = chunk_id
                chunks.append(current_chunk.copy())
                chunk_id += 1
                
                # Tạo chunk mới
                current_chunk = {
                    "chunk_id": chunk_id,
                    "content": "",
                    "tables": [],
                    "metadata": {
                        "source": str(docx_path),
                        "type": "text"
                    }
                }
        
        # Kiểm tra nếu là table
        elif element.tag.endswith('tbl'):
            table = Table(element, doc)
            latex_table = table_to_latex(table)
            
            # Lưu chunk hiện tại nếu có content
            if current_chunk["content"]:
                current_chunk["chunk_id"] = chunk_id
                chunks.append(current_chunk.copy())
                chunk_id += 1
            
            # Tạo chunk riêng cho table
            table_chunk = {
                "chunk_id": chunk_id,
                "content": "",
                "tables": [latex_table],
                "metadata": {
                    "source": str(docx_path),
                    "type": "table"
                }
            }
            chunks.append(table_chunk)
            chunk_id += 1
            
            # Reset chunk hiện tại
            current_chunk = {
                "chunk_id": chunk_id,
                "content": "",
                "tables": [],
                "metadata": {
                    "source": str(docx_path),
                    "type": "text"
                }
            }
    
    # Lưu chunk cuối cùng nếu còn content
    if current_chunk["content"] or current_chunk["tables"]:
        current_chunk["chunk_id"] = chunk_id
        chunks.append(current_chunk)
    
    return chunks


def main():
    """Main function."""
    import argparse
    
    # Fix encoding for Windows console
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    
    parser = argparse.ArgumentParser(
        description="Parse văn bản từ .docx sang JSON chunks cho RAG"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Đường dẫn file .docx đầu vào"
    )
    parser.add_argument(
        "--output",
        help="Đường dẫn file .json đầu ra (mặc định: cùng tên với input)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Kích thước tối đa của mỗi chunk (số ký tự)"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Lỗi: File không tồn tại: {input_path}")
        return
    
    # Xác định output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".json")
    
    print(f"Đang parse file: {input_path.name}")
    
    # Parse document thành chunks
    chunks = create_chunks_for_rag(str(input_path), args.chunk_size)
    
    # Tạo output structure
    result = {
        "document_metadata": {
            "source_file": str(input_path),
            "total_chunks": len(chunks),
            "chunk_size": args.chunk_size
        },
        "chunks": chunks
    }
    
    # Lưu kết quả
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"Đã lưu kết quả vào: {output_path.name}")
    print(f"Tổng số chunks: {len(chunks)}")
    
    # Thống kê
    text_chunks = sum(1 for c in chunks if c["metadata"]["type"] == "text")
    table_chunks = sum(1 for c in chunks if c["metadata"]["type"] == "table")
    print(f"  - Text chunks: {text_chunks}")
    print(f"  - Table chunks: {table_chunks}")


if __name__ == "__main__":
    main()
