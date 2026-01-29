"""
Script để parse văn bản pháp luật từ file .docx thành JSON
với cấu trúc chương, điều, khoản phục vụ RAG.
Bảng biểu sẽ được chuyển thành LaTeX tabular format.
"""

import re
import json
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
            # Thay newline trong cell bằng \\
            cell_text = cell_text.replace("\n", "\n")
            cells.append(cell_text)
        
        # Nối các cell với &
        row_text = " & ".join(cells) + " \\\\\\\\"
        latex_lines.append(row_text)
        latex_lines.append("\\hline")
    
    latex_lines.append("\\end{tabular}")
    return "\n".join(latex_lines)


def detect_structure_type(text: str) -> Dict[str, Any]:
    """
    Phát hiện loại cấu trúc của đoạn văn bản (chương, điều, khoản, điểm).
    """
    text = text.strip()
    
    # Pattern cho Chương
    chapter_patterns = [
        r'^Chương\s+([IVXLCDM]+|[0-9]+)[\.\s:]*(.+)?$',
        r'^CHƯƠNG\s+([IVXLCDM]+|[0-9]+)[\.\s:]*(.+)?$',
    ]
    
    # Pattern cho Điều
    article_patterns = [
        r'^Điều\s+(\d+)[\.\s:]*(.+)?$',
        r'^ĐIỀU\s+(\d+)[\.\s:]*(.+)?$',
    ]
    
    # Pattern cho Khoản (số đầu dòng)
    clause_patterns = [
        r'^(\d+)[\.\)]\s+(.+)$',
    ]
    
    # Pattern cho Điểm (chữ cái đầu dòng)
    point_patterns = [
        r'^([a-zđ])[\.\)]\s+(.+)$',
    ]
    
    # Kiểm tra Chương
    for pattern in chapter_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return {
                "type": "chapter",
                "number": match.group(1),
                "title": match.group(2).strip() if match.group(2) else ""
            }
    
    # Kiểm tra Điều
    for pattern in article_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return {
                "type": "article",
                "number": int(match.group(1)),
                "title": match.group(2).strip() if match.group(2) else ""
            }
    
    # Kiểm tra Khoản
    for pattern in clause_patterns:
        match = re.match(pattern, text)
        if match:
            return {
                "type": "clause",
                "number": int(match.group(1)),
                "content": match.group(2).strip()
            }
    
    # Kiểm tra Điểm
    for pattern in point_patterns:
        match = re.match(pattern, text)
        if match:
            return {
                "type": "point",
                "letter": match.group(1),
                "content": match.group(2).strip()
            }
    
    return {"type": "content", "text": text}


def parse_docx_to_json(docx_path: str) -> Dict[str, Any]:
    """
    Parse file .docx thành cấu trúc JSON với chương, điều, khoản.
    """
    doc = Document(docx_path)
    
    # Metadata
    result = {
        "document_metadata": {
            "title": "",
            "decision_number": "",
            "issued_date": "",
            "source_file": str(docx_path),
            "attachments": []
        },
        "chapters": []
    }
    
    # Biến để theo dõi cấu trúc hiện tại
    current_chapter = None
    current_article = None
    current_clause = None
    current_point = None
    
    # Biến để tích lũy title của document
    title_lines = []
    in_content = False
    
    # Xử lý từng element trong document
    for element in doc.element.body:
        # Kiểm tra nếu là paragraph
        if element.tag.endswith('p'):
            para = Paragraph(element, doc)
            text = para.text.strip()
            
            if not text:
                continue
            
            # Phát hiện cấu trúc
            structure = detect_structure_type(text)
            
            if structure["type"] == "chapter":
                in_content = True
                # Tạo chapter mới
                current_chapter = {
                    "chapter_number": structure["number"],
                    "chapter_title": structure["title"],
                    "articles": []
                }
                result["chapters"].append(current_chapter)
                current_article = None
                current_clause = None
                current_point = None
                
            elif structure["type"] == "article":
                in_content = True
                # Tạo article mới
                current_article = {
                    "article_number": structure["number"],
                    "article_id": f"dieu_{structure['number']}",
                    "article_title": structure["title"],
                    "clauses": [],
                    "legal_reference": {
                        "chapter": current_chapter["chapter_number"] if current_chapter else None,
                        "article": structure["number"]
                    }
                }
                
                # Nếu chưa có chapter, tạo chapter mặc định
                if not current_chapter:
                    current_chapter = {
                        "chapter_number": None,
                        "chapter_title": "",
                        "articles": []
                    }
                    result["chapters"].append(current_chapter)
                
                current_chapter["articles"].append(current_article)
                current_clause = None
                current_point = None
                
            elif structure["type"] == "clause":
                in_content = True
                # Tạo clause mới
                current_clause = {
                    "clause_number": structure["number"],
                    "clause_id": f"khoan_{structure['number']}",
                    "points": [],
                    "latex_tables": [],
                    "content": structure["content"]
                }
                
                if current_article:
                    current_article["clauses"].append(current_clause)
                current_point = None
                
            elif structure["type"] == "point":
                in_content = True
                # Tạo point mới
                current_point = {
                    "point_letter": structure["letter"],
                    "content": structure["content"]
                }
                
                if current_clause:
                    current_clause["points"].append(current_point)
                
            elif structure["type"] == "content":
                # Content text - append vào element hiện tại
                if not in_content:
                    # Phần đầu văn bản - có thể là title
                    title_lines.append(text)
                elif current_point:
                    # Append vào point
                    current_point["content"] += "\n" + text
                elif current_clause:
                    # Append vào clause
                    current_clause["content"] += "\n" + text
                elif current_article:
                    # Append vào article title hoặc tạo clause mặc định
                    if not current_article["clauses"]:
                        current_article["clauses"].append({
                            "clause_number": 1,
                            "clause_id": "khoan_1",
                            "points": [],
                            "latex_tables": [],
                            "content": text
                        })
                    else:
                        current_article["clauses"][-1]["content"] += "\n" + text
        
        # Kiểm tra nếu là table
        elif element.tag.endswith('tbl'):
            table = Table(element, doc)
            latex_table = table_to_latex(table)
            
            # Thêm table vào phần tử hiện tại
            if current_clause:
                current_clause["latex_tables"].append(latex_table)
            elif current_article:
                # Tạo clause mặc định nếu chưa có
                if not current_article["clauses"]:
                    current_article["clauses"].append({
                        "clause_number": 1,
                        "clause_id": "khoan_1",
                        "points": [],
                        "latex_tables": [latex_table],
                        "content": ""
                    })
                else:
                    current_article["clauses"][-1]["latex_tables"].append(latex_table)
            else:
                # Table ở đầu document - thêm vào attachments
                result["document_metadata"]["attachments"].append({
                    "latex_table": latex_table
                })
    
    # Set document title từ title_lines
    if title_lines:
        result["document_metadata"]["title"] = "\n".join(title_lines)
    
    return result


def main():
    """Main function để parse document."""
    import argparse
    import sys
    
    # Fix encoding for Windows console
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    
    parser = argparse.ArgumentParser(
        description="Parse văn bản pháp luật từ .docx sang JSON"
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
    
    print(f"Đang parse file: {input_path}")
    
    # Parse document
    result = parse_docx_to_json(str(input_path))
    
    # Lưu kết quả
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"Đã lưu kết quả vào: {output_path}")
    print(f"Số chương: {len(result['chapters'])}")
    
    total_articles = sum(len(ch["articles"]) for ch in result["chapters"])
    print(f"Tổng số điều: {total_articles}")


if __name__ == "__main__":
    main()
