import sqlite3
import pathlib
import json
import sys

# Çapraz platform uyumluluğu için projenin ana dizinini buluyoruz
# Bu sayede Windows'ta (C:\) veya Mac/Linux'ta (/) yol hatası almayız
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

# schemas.py dosyasını içe aktarabilmek için ana dizini Python yoluna ekliyoruz
sys.path.append(str(BASE_DIR))

try:
    from schemas import TaskStatus, FrameData, SummaryResult
except ImportError:
    print("Uyarı: schemas.py bulunamadı. Lütfen ana dizinde olduğundan emin olun.")

class DatabaseManager:
    def __init__(self, db_name: str = "vision_context.db"):
        # Veritabanı dosyası database/ klasörü içinde oluşacak
        self.db_path = BASE_DIR / "database" / db_name
        self._initialize_db()

    def _get_connection(self):
        """SQLite bağlantısı oluşturur."""
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        """Tabloları kontrol eder ve yoksa oluşturur."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. İş Kuyruğu Tablosu (State Machine için)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    image_path TEXT NOT NULL,
                    ocr_status TEXT DEFAULT 'PENDING',
                    audio_status TEXT DEFAULT 'PENDING',
                    vlm_status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Anlamsal Hafıza Tablosu (FTS5 ile Full-Text Search)
            # Not: FTS5 tablolarında veri tipleri (TEXT, INT) belirtilmez, her şey metindir.
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_memory USING fts5(
                    video_name,
                    timestamp,
                    ocr_text,
                    transcript_text,
                    summary,
                    embedding
                )
            """)
            
            conn.commit()

    def add_to_queue(self, frame_data: FrameData) -> int:
        """Yeni yakalanan bir kareyi asenkron işlenmesi için kuyruğa ekler."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processing_queue 
                (video_name, timestamp, image_path, ocr_status, audio_status, vlm_status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                frame_data.video_name, 
                frame_data.timestamp, 
                frame_data.image_path,
                TaskStatus.PENDING.value,
                TaskStatus.PENDING.value,
                TaskStatus.PENDING.value
            ))
            conn.commit()
            return cursor.lastrowid

    def video_already_processed(self, video_name: str) -> bool:
        """
        Bu video daha önce kuyruğa hiç eklenmiş mi kontrol eder.

        Neden gerekli: frame_extractor.py aynı videoyu tekrar çalıştırdığında
        (örn. geliştirme sırasında test için tekrar tekrar çalıştırmak) aynı kareleri
        tekrar kuyruğa atıp semantic_memory tablosunda birebir aynı içerik için
        duplicate satırlar biriktiriyordu. Bu kontrol sayesinde frame_extractor
        önce kontrol edip gerekirse işlemi atlayabiliyor (force=True ile bilerek
        tekrar işlenebilir, ör. video güncellendiyse).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processing_queue WHERE video_name = ? LIMIT 1",
                (video_name,)
            )
            return cursor.fetchone() is not None

    def save_semantic_memory(self, video_name: str, timestamp: float, ocr_text: str, transcript_text: str, summary_result: SummaryResult):
        """İşlemi tamamlanan kareyi ana hafıza tablosuna kaydeder ve kuyruğu günceller."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Vektör verisini (embedding) SQLite'ta tutabilmek için JSON formatına çeviriyoruz
            embedding_str = json.dumps(summary_result.embedding) if summary_result.embedding else None
            
            # 1. FTS5 tablosuna final verisini yaz
            cursor.execute("""
                INSERT INTO semantic_memory 
                (video_name, timestamp, ocr_text, transcript_text, summary, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                video_name, 
                str(timestamp), 
                ocr_text, 
                transcript_text, 
                summary_result.summary, 
                embedding_str
            ))
            
            # 2. Kuyruktaki işlemin durumunu 'COMPLETED' olarak güncelle
            cursor.execute("""
                UPDATE processing_queue 
                SET vlm_status = ? 
                WHERE id = ?
            """, (TaskStatus.COMPLETED.value, summary_result.frame_id))
            
            conn.commit()

# Test amaçlı kullanım (Dosya doğrudan çalıştırıldığında hata vermemesi için)
if __name__ == "__main__":
    db = DatabaseManager()
    print(f"Veritabanı başarıyla şu yolda oluşturuldu/bağlandı: {db.db_path}")