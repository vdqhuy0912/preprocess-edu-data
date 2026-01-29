"""Sử dụng format đầu ra của models."""

from pydantic import BaseModel, Field
import enum

class ReasoningLevel(str, enum.Enum):
    NO_REASONING = "0"  # no reasoning needed
    LOW = "1"  # 1-2 steps of reasoning 
    MEDIUM = "2"  # more than 3 steps of reasoning



class Topic(str, enum.Enum):
    XTT_UTXT = "XTT & ƯTXT"
    XT_THPTQG = "XT THPT QG"
    XT_COMBINED = "XT kết hợp"
    XT_KHAC = "XT khác"
    KHONG_XT = "Không XT"
    HO_SO_QUY_TRINH = "Hồ sơ và quy trình"
    INFO_TS_KHAC = "Thông tin tuyển sinh khác"
    INFO_NHAP_HOC = "Thông tin nhập học"
    CHUONG_TRINH_HOC = "Chương trình học"
    DBCL = "ĐBCL"
    KHONG_LIEN_QUAN = "Không liên quan"


class QuestionType(str, enum.Enum):
    WHAT = "Cái gì"
    WHO = "Ai"
    WHERE = "Ở đâu"
    WHEN = "Khi nào"
    HOW = "Như thế nào"
    HOW_MANY = "Bao nhiêu"
    WHY = "Tại sao" 
    YES_NO = "Có/Không"


class Message(BaseModel):
    """Một tin nhắn trong hội thoại."""
    role: str = Field(description="Role: 'user' hoặc 'assistant'")
    content: str = Field(description="Nội dung tin nhắn")


class QAOutput(BaseModel):
    """Output schema cho việc tái cấu trúc conversation."""
    dialog_id: str = Field(description="ID của dialog, format: dialog_id_<thứ tự intent>")
    topic: Topic = Field(description="Chủ đề của Q&A")
    messages: list[Message] = Field(description="Danh sách tin nhắn user và assistant")
    multi_intent: bool = Field(description="True nếu questions cùng topic được gộp")
    insufficient_context: bool = Field(description="True nếu câu hỏi thiếu ngữ cảnh")
    question_type: QuestionType = Field(description="Loại câu hỏi")
    reasoning_level: ReasoningLevel = Field(description="Mức độ suy luận")