from pydantic import BaseModel
from enum import Enum
from typing import Optional

# İşlem kuyruğundaki durumları (State Machine) belirleyen sınıf
class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# OpenCV'nin üreteceği, veritabanına ilk girecek ham veri
class FrameData(BaseModel):
    video_name: str
    timestamp: float
    image_path: str

# Worker (İşçi) modülünün OCR ve Whisper'dan toplayıp VLM'e göndereceği veri
class ExtractedData(BaseModel):
    frame_id: int
    image_path: str
    ocr_text: Optional[str] = ""
    transcript_text: Optional[str] = ""

# VLM'in özetleme işlemi sonrasında veritabanına kaydedilecek son veri
class SummaryResult(BaseModel):
    frame_id: int
    summary: str
    embedding: Optional[list[float]] = None