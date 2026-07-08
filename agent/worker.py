import time
import pathlib
import sys
import json
import easyocr
from sentence_transformers import SentenceTransformer

# Çapraz platform ve modül entegrasyonu ayarları
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from database.db_manager import DatabaseManager
from schemas import SummaryResult, TaskStatus
from vision.audio_processor import AudioProcessor
from agent.vlm_providers import get_vlm_provider
from config import settings

class BackgroundWorker:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.audio_processor = AudioProcessor()
        # VLM sağlayıcısı artık config.py'deki VLM_PROVIDER ayarına göre seçiliyor.
        # "ollama" (yerel model) veya "anthropic" (API) arasında .env dosyasından
        # tek satır değiştirerek geçiş yapılabilir, kod değişmez.
        self.vlm_provider = get_vlm_provider(settings)
        print(f"VLM sağlayıcı: {settings.vlm_provider} (model: {settings.vlm_model if settings.vlm_provider == 'ollama' else settings.anthropic_model})")
        # Video başına ses dökümü (transcript) cache'i. Aynı videoya ait onlarca
        # frame işlenirken her seferinde aynı .json dosyasını diskten okumamak için.
        self._audio_cache: dict[str, list] = {}
        print("EasyOCR modeli yükleniyor... (İlk seferde model dosyalarını indireceği için 1-2 dakika sürebilir)")
        # Türkçe ve İngilizce dillerini okuyabilen modeli başlatıyoruz.
        # Eğer bilgisayarında NVIDIA ekran kartı varsa 'gpu=True' yapabilirsin.
        self.reader = easyocr.Reader(['tr', 'en'], gpu=False)
        print("Embedding modeli (all-MiniLM-L6-v2) yükleniyor... (İlk seferde ~80MB indirecektir)")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

    def get_pending_task(self):
        """Veritabanından işlenmeyi bekleyen ilk görevi çeker."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, video_name, timestamp, image_path 
                FROM processing_queue 
                WHERE vlm_status = ? 
                ORDER BY created_at ASC LIMIT 1
            """, (TaskStatus.PENDING.value,))
            return cursor.fetchone()

    def mark_task_status(self, task_id: int, status: TaskStatus):
        """Kuyruktaki görevin durumunu günceller."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processing_queue 
                SET vlm_status = ? 
                WHERE id = ?
            """, (status.value, task_id))
            conn.commit()

    def extract_text(self, image_path: str) -> str:
        """Gerçek EasyOCR kullanarak görseldeki metni okur."""
        try:
            # Görseli okuyup içindeki metin bloklarını birleştiriyoruz
            results = self.reader.readtext(image_path)
            extracted = " ".join([res[1] for res in results])
            return extracted
        except Exception as e:
            print(f"  [!] OCR Hatası: {str(e)}")
            return ""
        
    def get_audio_context(self, video_name: str, timestamp: float, duration: float = 2.0) -> str:
        """
        Belirtilen saniyedeki (timestamp) konuşmaları, +/- duration saniye aralığında arar ve döndürür.
        """
        # Cache'te varsa diski hiç dokunmadan devam et
        if video_name in self._audio_cache:
            segments = self._audio_cache[video_name]
        else:
            audio_path = BASE_DIR / "output_audio" / f"{video_name}.json"

            # Eğer bu video için daha önce ses dökümü (json) oluşturulmadıysa boş dön
            if not audio_path.exists():
                self._audio_cache[video_name] = []
                return ""

            try:
                with open(audio_path, 'r', encoding='utf-8') as f:
                    segments = json.load(f)
                self._audio_cache[video_name] = segments
            except Exception as e:
                print(f"  [!] Ses dökümü okunamadı: {str(e)}")
                self._audio_cache[video_name] = []
                return ""

        try:
            relevant_text = []
            for segment in segments:
                # ESKI MANTIK HATALIYDI: sadece segmentin start/end'i timestamp'e
                # "duration" kadar yakınsa alıyordu. Bu yüzden örneğin 0-10sn süren bir
                # konuşma segmenti varsa ve görsel 5. saniyedeyse (segment ortası),
                # ne start'a ne end'e 2 saniye içinde olduğu için tamamen atlanıyordu.
                # Doğrusu: [timestamp-duration, timestamp+duration] aralığı ile
                # [segment.start, segment.end] aralığının kesişip kesişmediğine bakmak.
                window_start = timestamp - duration
                window_end = timestamp + duration
                if segment['start'] <= window_end and segment['end'] >= window_start:
                    relevant_text.append(segment['text'])
                    
            return " ".join(relevant_text).strip()
        except Exception as e:
            print(f"  [!] Ses dökümü okunamadı: {str(e)}")
            return ""

    def run(self):
        """Sürekli arka planda çalışarak kuyruğu dinleyen ana döngü."""
        print("Zeki İşçi (Worker) başlatıldı. Kuyruk dinleniyor...")
        
        while True:
            task = self.get_pending_task()
            
            if task:
                task_id, video_name, timestamp, image_path = task
                print(f"\n[İŞLEM BAŞLADI] Görev ID: {task_id} | Saniye: {timestamp}")
                
                try:
                    self.mark_task_status(task_id, TaskStatus.PROCESSING)
                    
                    print("  -> EasyOCR görseli okuyor...")
                    ocr_text = self.extract_text(image_path)
                    
                    print("  -> İşitsel hafıza taranıyor...")
                    transcript_text = self.get_audio_context(video_name, timestamp)
                    if transcript_text:
                        print(f"  -> Konuşma Yakalandı: {transcript_text[:50]}...")
                    
                    print("  -> VLM ile bağlam çıkarılıyor...")
                    summary = self.vlm_provider.summarize(image_path, ocr_text, transcript_text)
                    print(f"  -> VLM Özet: {summary[:100]}...")
                    
                    print("  -> Anlamsal vektör (embedding) oluşturuluyor...")
                    embedding_vector = self.embedding_model.encode(summary).tolist()
                    
                    result = SummaryResult(
                        frame_id=task_id,
                        summary=summary,
                        embedding=embedding_vector
                    )
                    
                    self.db.save_semantic_memory(
                        video_name=video_name,
                        timestamp=timestamp,
                        ocr_text=ocr_text,
                        transcript_text=transcript_text,
                        summary_result=result
                    )
                    
                    print(f"[BAŞARILI] Görev {task_id} hafızaya işlendi.")
                    
                except Exception as e:
                    print(f"[HATA] Görev {task_id} çöktü: {str(e)}")
                    self.mark_task_status(task_id, TaskStatus.FAILED)
            else:
                time.sleep(2)

if __name__ == "__main__":
    db = DatabaseManager()
    worker = BackgroundWorker(db)
    worker.run()