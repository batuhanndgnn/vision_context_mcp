import cv2
import numpy as np
import pathlib
import sys

# Çapraz platform ve modül entegrasyonu ayarları
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

#  veritabanı sınıfını ve şemamızı içeri aktarıyoruz
from database.db_manager import DatabaseManager
from schemas import FrameData

class VideoProcessor:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        # Görsellerin geçici olarak birikeceği klasör
        self.output_dir = BASE_DIR / "output_frames"
        self.output_dir.mkdir(exist_ok=True) # Klasör yoksa otomatik oluştur

    def calculate_difference(self, frame1, frame2) -> float:
        """İki kare arasındaki piksellerin yüzde kaçının değiştiğini hesaplar."""
        if frame1 is None or frame2 is None:
            return 100.0 # İlk kare için her zaman %100 değişim kabul et

        # 1. Renkler işlemciyi yorar ve algoritmamızı yanıltabilir. iki kareyi de gri tonlamaya (Grayscale) çeviriyoruz.
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        # 2. İki gri görseli birbirinden çıkararak sadece değişen pikselleri bul
        diff = cv2.absdiff(gray1, gray2)
        
        # 3. Sıfırdan farklı (yani değişmiş) pikselleri say ve orantıla
        non_zero_count = np.count_nonzero(diff)
        total_pixels = diff.shape[0] * diff.shape[1]
        
        difference_percentage = (non_zero_count / total_pixels) * 100
        return difference_percentage

    def process_video(self, video_path: str, video_name: str, threshold: float = 15.0, force: bool = False):
        """Videoyu okur, değişen kareleri filtreler ve kuyruğa atar."""
        # IDEMPOTENCY KONTROLÜ: Bu video daha önce işlendiyse (kuyruğa eklendiyse)
        # varsayılan olarak tekrar işlemiyoruz. Aksi halde aynı videoyu her çalıştırmada
        # aynı kareler tekrar tekrar kuyruğa/veritabanına giriyor, veri şişkinliği
        # oluşturuyordu. Bilerek yeniden işlemek istersen force=True geç.
        if not force and self.db.video_already_processed(video_name):
            print(f"[{video_name}] Bu video daha önce işlenmiş, atlanıyor. "
                  f"Tekrar işlemek için process_video(..., force=True) kullan.")
            return

        print(f"[{video_name}] İşleniyor...")
        
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)

        # GÜVENLİK KALKANI: Video okunamadıysa işlemi güvenlice iptal et
        if not cap.isOpened() or fps == 0:
            print("HATA: Video açılamadı! Lütfen videonun standart H.264 MP4 formatında olduğundan emin olun.")
            cap.release()
            return
        
        # Saniyede 1 kare atlamak için kameranın kendi FPS değerini kullanıyoruz
        frame_jump = int(fps) 

        prev_frame = None
        current_frame_idx = 0

        while cap.isOpened():
            # Videoyu normal oynatmak yerine doğrudan hesapladığımız saniyeye atlıyoruz (Performans x10)
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
            ret, frame = cap.read()
            
            if not ret:
                break # Video bitti

            # Önceki kare ile yeni kare arasındaki farkı hesapla
            diff = self.calculate_difference(prev_frame, frame)
            
            # Eğer ekrandaki değişim bizim belirlediğimiz eşiği (%15) aştıysa:
            if diff > threshold:
                timestamp = current_frame_idx / fps
                
                # 1. Görseli kaydet
                # NOT: int(timestamp) kullanmıyoruz çünkü aynı saniye içinde birden fazla
                # değişim yakalanırsa (ör. 1.2s ve 1.8s) dosya adları çakışır ve önceki
                # kare sessizce üzerine yazılırdı. current_frame_idx video boyunca hep
                # artan/benzersiz olduğu için çakışma imkansız hale geliyor.
                image_filename = f"{video_name}_frame{current_frame_idx}_{timestamp:.2f}s.jpg"
                image_path = self.output_dir / image_filename
                cv2.imwrite(str(image_path), frame)
                
                # 2. Pydantic şemamıza uygun veri paketini oluştur
                frame_data = FrameData(
                    video_name=video_name,
                    timestamp=timestamp,
                    image_path=str(image_path)
                )
                
                # 3. SQLite veritabanındaki İş Kuyruğuna (processing_queue) ekle
                self.db.add_to_queue(frame_data)
                
                print(f"Yeni bağlam yakalandı: {timestamp:.1f}. saniye (Değişim: %{diff:.1f})")
                
                # Artık referans karemiz bu yeni görsel oldu
                prev_frame = frame 
            
            # Bir sonraki saniyeye geç
            current_frame_idx += frame_jump

        cap.release()
        print("Video filtreleme tamamlandı. Değerli kareler kuyruğa eklendi!")

if __name__ == "__main__":

    
     db = DatabaseManager()
     processor = VideoProcessor(db)
     processor.process_video("test.mp4", "ornek_video")
