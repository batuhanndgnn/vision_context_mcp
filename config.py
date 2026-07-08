"""
Merkezi konfigürasyon.

Neden bu dosya var: worker.py içinde os.getenv("VLM_MODEL", "moondream") gibi
dağınık, kod içine gömülü ayarlar vardı. Sektör standardında ayarlar TEK bir
yerden, tip-güvenli (type-safe) şekilde okunur. pydantic-settings bunu sağlıyor.

Kurulum: pip install pydantic-settings

Kullanım: proje kök dizinine bir ".env" dosyası koy, örnek:

    VLM_PROVIDER=ollama
    VLM_MODEL=moondream
    OLLAMA_HOST=http://localhost:11434

    # veya API ile çalışmak istersen:
    VLM_PROVIDER=anthropic
    ANTHROPIC_API_KEY=sk-ant-...
    ANTHROPIC_MODEL=claude-haiku-4-5-20251001
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "ollama" = yerelde çalışan bir model (moondream, llama3.2-vision, vb.)
    # "anthropic" = Anthropic API üzerinden Claude ile (internet + API key gerekir)
    vlm_provider: Literal["ollama", "anthropic"] = "ollama"

    # --- Ollama ayarları ---
    vlm_model: str = "moondream"
    ollama_host: str = "http://localhost:11434"

    # --- Anthropic API ayarları ---
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-haiku-4-5-20251001"


settings = Settings()

if __name__ == "__main__":
    print("Aktif ayarlar:")
    print(settings.model_dump())
