"""
VLM (Vision-Language Model) sağlayıcı soyutlaması.

Neden bu dosya var: worker.py içinde generate_vlm_summary metodu direkt
"http://localhost:11434" adresine hardcoded istek atıyordu. Bu yüzden proje
sadece Ollama ile çalışabiliyordu. Word dosyasındaki orijinal plan zaten
"Lokal VLM (Qwen-VL) veya API" diyordu — yani kullanıcı istediği zaman
yerel modelle, istediği zaman bir API ile çalışabilmeli.

Bu dosya bunu sağlıyor: her sağlayıcı (provider) aynı arayüzü (summarize)
uyguluyor, worker.py hangi sağlayıcının çalıştığını hiç bilmiyor/bilmesi
gerekmiyor. Yeni bir sağlayıcı eklemek istersen (ör. OpenAI GPT-4V) sadece
bu dosyaya yeni bir sınıf eklersin, worker.py'ye dokunmazsın.
"""
from abc import ABC, abstractmethod
import base64
import io
from PIL import Image
import requests


def _build_prompt(ocr_text: str, transcript_text: str) -> str:
    """Tüm sağlayıcıların ortak kullandığı prompt. Tek yerden yönetilsin diye ayrı fonksiyon."""
    return (
        "Analyze this technical video frame. "
        f"On-screen text: '{ocr_text}'. "
        f"Speaker says: '{transcript_text}'. "
        "Briefly summarize what is shown on screen and what the speaker is explaining, in Turkish."
    )


def _load_thumbnail_b64(image_path: str, size: tuple[int, int] = (768, 768)) -> str:
    """Görseli küçültüp base64'e çevirir. Tüm sağlayıcılar aynı formatı istiyor."""
    img = Image.open(image_path)
    img.thumbnail(size)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class VLMProvider(ABC):
    """Tüm sağlayıcıların uyması gereken ortak arayüz."""

    @abstractmethod
    def summarize(self, image_path: str, ocr_text: str, transcript_text: str) -> str:
        """Görsel + OCR metni + konuşma metnini alır, Türkçe özet metni döndürür.
        Hata durumunda exception fırlatmaz, kullanıcı dostu bir hata string'i döner
        (worker.py'nin try/except mantığıyla uyumlu olması için)."""
        ...


class OllamaVLMProvider(VLMProvider):
    """Yerelde çalışan Ollama üzerinden (moondream, llama3.2-vision, vb.)."""

    def __init__(self, model: str, host: str):
        self.model = model
        self.host = host

    def summarize(self, image_path: str, ocr_text: str, transcript_text: str) -> str:
        try:
            encoded_image = _load_thumbnail_b64(image_path)
            prompt_text = _build_prompt(ocr_text, transcript_text)

            payload = {
                "model": self.model,
                "prompt": prompt_text,
                "images": [encoded_image],
                "stream": False,
            }

            response = requests.post(f"{self.host}/api/generate", json=payload, timeout=300)
            response.raise_for_status()

            result = response.json().get("response", "")
            return result.strip() if result else "VLM boş yanıt döndürdü."

        except requests.exceptions.Timeout:
            return "HATA: Ollama modelinden yanıt alınamadı (300sn Zaman Aşımı)."
        except requests.exceptions.ConnectionError:
            return "HATA: Ollama API'sine bağlanılamadı. Arka planda Ollama'nın çalıştığından emin olun."
        except Exception as e:
            return f"Model veya işleme hatası (Ollama): {str(e)}"


class AnthropicVLMProvider(VLMProvider):
    """Anthropic API üzerinden (internet + ANTHROPIC_API_KEY gerekir).
    Yerel donanımın zayıfsa veya moondream gibi küçük modellerin kalitesi
    yetmiyorsa bu seçenek çok daha tutarlı özetler üretir."""

    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY tanımlı değil. .env dosyana ANTHROPIC_API_KEY=sk-ant-... ekle."
            )
        self.api_key = api_key
        self.model = model

    def summarize(self, image_path: str, ocr_text: str, transcript_text: str) -> str:
        try:
            import anthropic  # pip install anthropic
        except ImportError:
            return "HATA: 'anthropic' paketi kurulu değil. 'pip install anthropic' çalıştır."

        try:
            encoded_image = _load_thumbnail_b64(image_path)
            prompt_text = _build_prompt(ocr_text, transcript_text)

            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": encoded_image,
                                },
                            },
                            {"type": "text", "text": prompt_text},
                        ],
                    }
                ],
            )
            text_blocks = [block.text for block in message.content if block.type == "text"]
            result = " ".join(text_blocks).strip()
            return result if result else "VLM boş yanıt döndürdü."

        except Exception as e:
            return f"Model veya işleme hatası (Anthropic API): {str(e)}"


def get_vlm_provider(settings) -> VLMProvider:
    """config.py'deki settings'e bakıp doğru sağlayıcıyı üretir (factory pattern).
    worker.py sadece bu fonksiyonu çağırır, hangi sınıfın döndüğünü bilmesi gerekmez."""
    if settings.vlm_provider == "ollama":
        return OllamaVLMProvider(model=settings.vlm_model, host=settings.ollama_host)
    elif settings.vlm_provider == "anthropic":
        return AnthropicVLMProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    else:
        raise ValueError(f"Bilinmeyen VLM_PROVIDER: {settings.vlm_provider}")
