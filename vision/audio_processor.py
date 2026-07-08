import whisper
import ffmpeg
import pathlib
import sys
import os

# Çapraz platform uyumluluğu için ana dizini belirliyoruz
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

class AudioProcessor:
    def __init__(self, model_size="base"):
        # Whisper modelini yüklüyoruz. 'base' modeli hız ve doğruluk açısından optimumdur.
        print(f"Whisper '{model_size}' modeli yükleniyor... (İlk seferde 70-140MB indirebilir)")
        self.model = whisper.load_model(model_size)
        
        # Ayrıştırılan seslerin tutulacağı klasör
        self.audio_dir = BASE_DIR / "output_audio"
        self.audio_dir.mkdir(exist_ok=True)

    def extract_audio(self, video_path: str, video_name: str) -> str:
        """FFmpeg kullanarak videonun sesini saf ve hafif bir .wav dosyasına ayırır."""
        audio_path = self.audio_dir / f"{video_name}.wav"
        
        if audio_path.exists():
            print(f"[{video_name}] Ses dosyası zaten mevcut, doğrudan okumaya geçiliyor.")
            return str(audio_path)
            
        print(f"[{video_name}] Videodan ses ayrıştırılıyor (FFmpeg devrede)...")
        try:
            (
                ffmpeg
                .input(video_path)
                .output(str(audio_path), acodec='pcm_s16le', ac=1, ar='16k')
                .overwrite_output()
                .run(quiet=True, capture_stderr=True) # Hata mesajlarını yakalamak için capture_stderr ekledik
            )
            return str(audio_path)
        except ffmpeg.Error as e:
            # FFmpeg'den dönen byte formatındaki hatayı metne çeviriyoruz
            hata_mesaji = e.stderr.decode('utf-8', errors='ignore') if e.stderr else ""
            
            # Eğer hata "ses kanalı yok" hatasıysa, sistemi çökertmeden sessizce geç
            if "Output file does not contain any stream" in hata_mesaji:
                print(f"[{video_name}] UYARI: Bu videoda ses kanalı bulunmuyor (Sessiz Video). İşitsel hafıza atlanıyor.")
                return ""
            else:
                print(f"[!] FFmpeg Hatası: {hata_mesaji}")
                return ""

    def transcribe_audio(self, audio_path: str):
        """Whisper ile sesi dinler ve zaman damgalı JSON formatında metne döker."""
        # Eğer ses dosyası yoksa (sessiz video), boş liste dön
        if not audio_path:
            return []
            
        print("-> Whisper sesi dinliyor ve metne döküyor...")
        result = self.model.transcribe(audio_path, fp16=False)
        print("-> İşitsel döküm tamamlandı!")
        return result["segments"]

# Test Bloğu
if __name__ == "__main__":
    import json
    video_dosyasi = str(BASE_DIR / "test.mp4")
    video_adi = "ornek_video"
    
    if os.path.exists(video_dosyasi):
        processor = AudioProcessor()
        wav_yolu = processor.extract_audio(video_dosyasi, video_adi)
        
        if wav_yolu:
            konusmalar = processor.transcribe_audio(wav_yolu)
            
            # Konuşmaları Worker'ın okuyabilmesi için JSON olarak kaydet
            json_yolu = BASE_DIR / "output_audio" / f"{video_adi}.json"
            with open(json_yolu, 'w', encoding='utf-8') as f:
                json.dump(konusmalar, f, ensure_ascii=False, indent=4)
                
            print(f"\n[BAŞARILI] İşitsel döküm '{json_yolu}' dosyasına kaydedildi.")
    else:
        print(f"HATA: {video_dosyasi} bulunamadı. Lütfen ana dizinde bir test.mp4 olduğundan emin olun.")