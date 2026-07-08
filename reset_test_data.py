"""
Geliştirme/test sırasında biriken kuyruk ve hafıza verilerini temizler.

Neden gerekli: frame_extractor.py'yi defalarca çalıştırmak (idempotency fix'i
gelmeden önce) processing_queue ve semantic_memory tablolarında aynı videonun
tekrar tekrar işlenmiş kopyalarını biriktirdi. Bu script veritabanını sıfırlar,
gerçek/temiz bir testin önünü açar.

DİKKAT: Bu script processing_queue ve semantic_memory tablolarındaki TÜM
satırları siler. Gerçek kullanımda (production'da) çalıştırma — sadece
geliştirme ortamında, bilerek sıfırlamak istediğinde kullan.

Kullanım:
    python reset_test_data.py
"""
from database.db_manager import DatabaseManager


def main():
    db = DatabaseManager()
    with db._get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM processing_queue")
        queue_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM semantic_memory")
        memory_count = cursor.fetchone()[0]

        print(f"Silinecek: {queue_count} kuyruk kaydı, {memory_count} hafıza kaydı.")
        onay = input("Devam etmek istiyor musun? (evet/hayır): ").strip().lower()

        if onay not in ("evet", "e", "yes", "y"):
            print("İptal edildi, hiçbir şey silinmedi.")
            return

        cursor.execute("DELETE FROM processing_queue")
        cursor.execute("DELETE FROM semantic_memory")
        conn.commit()

        print("Veritabanı temizlendi. Şimdi 'python vision/frame_extractor.py' ile "
              "temiz bir test yapabilirsin.")


if __name__ == "__main__":
    main()
