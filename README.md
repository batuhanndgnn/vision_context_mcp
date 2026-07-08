Proje Başlangıç Raporu: Vision-Context MCP v2 (Otonom Görsel ve İşitsel Hafıza Ajanı)
1. Projenin Vizyonu ve Değer Önerisi
Geliştiriciler ve mühendisler her gün saatlerce teknik video, toplantı kaydı veya mimari sunum izler. Ancak bu görsel ve işitsel veriler "akıp gidicidir"; izlendikten sonra kaybolur ve LLM'ler (Claude, Cursor vb.) tarafından içeriği bilinemez.
Vision-Context MCP, izlenen video kayıtlarını otonom olarak işleyen, gereksiz kareleri çöpe atan, önemli anları (mimari çizimler, kodlar) ve o esnada konuşulanları (audio context) Görsel Dil Modelleri (VLM) ile harmanlayarak anlamsal olarak özetleyen yerel bir ajan sistemidir. Bu veriler, LLM'lerin hem kelime hem de anlam (vektör) bazlı sorgulayabileceği, geliştiriciye özel bir bilgi tabanına dönüştürülür.
2. Düzeltilmiş ve Optimize Edilmiş Sistem Mimarisi (Asenkron Pipeline)
Katman	Görev	Teknoloji / Araç
1. Video & Audio Ingestion	Videoyu saniyede 1 kare (1 FPS) ile okur. Eşzamanlı olarak ses dosyasını videodan ayırır.	OpenCV + FFmpeg
2. Frame Decimation (Filtreleme)	İki kare arasındaki yapısal farkı hesaplar. Ekran değişmediyse kareyi çöpe atar.	OpenCV (SSIM / Frame Differencing)
3. Audio Transcription (İşitsel Hafıza)	Ayrılan ses dosyasını arka planda zaman damgalarıyla (timestamp) metne döker.	Whisper.cpp veya Whisper-tiny
4. Lightweight Triage	Değişen karenin boş bir yüz mü yoksa bilgi içeren bir slayt/kod mu olduğunu hızlıca ayırır.	YOLOv8-Nano
5. Deep Extraction (Anlamlandırma)	Görseldeki metinleri (OCR), o saniyedeki konuşma metni (Transcript) ile birleştirip VLM'e "Bu anı özetle" diyerek bağlamı çıkarır.	EasyOCR + Lokal VLM (Qwen-VL) veya API
6. Semantic Memory (Hibrit Hafıza)	Video adı, zaman damgası, görsel/ses özeti ve bu özetin "vektör karşılığını (embedding)" hızlı arama için kaydeder.	SQLite (FTS5 + sqlite-vec veya sqlite-vss) + all-MiniLM-L6-v2
7. MCP Server (Ajan Arayüzü)	Claude veya Cursor IDE'ye bu veritabanında hem kelime (FTS5) hem anlam (Vektör) araması yapma yeteneği verir.	Model Context Protocol (Python SDK)
3. Geliştirme Süreci ve Yol Haritası (Fazlar)
Faz 1: Görüntü ve Ses Ayrıştırma Çekirdeği (Core Vision & Audio)
Amacın videoyu parçalamak ve değişimleri yakalamak.
•	OpenCV ile her 30 karede bir (1 saniye) okuma yapan döngüyü yaz. Gri tonlama ve %15 fark kuralıyla değişen kareleri output_frames/ klasörüne zaman damgasıyla kaydet.
•	Python subprocess veya ffmpeg-python ile videonun sesini baştan tek seferde ayrıştırıp .wav olarak kaydet.
Faz 2: İşitsel ve Metinsel Çıkarım (Extraction & Transcription)
Verileri anlamlandırma hazırlığı.
•	output_frames/ klasörüne düşen resimler için EasyOCR çalıştır (Producer-Consumer mantığı ile arka planda).
•	Ayrılan .wav dosyasını Whisper modeline vererek zaman damgalı .json formatında dökümünü (transcript) al.
Faz 3: Hibrit Veritabanı (SQLite FTS5 + Vektör)
Hafıza merkezini kurma aşaması.
•	SQLite veritabanı kur. Hem FTS5 tablosu (kelime araması için) hem de Vektör tablosu (sqlite-vec ile) oluştur. Sütunlar: id, video_name, timestamp, ocr_text, transcript_text, summary, embedding, image_path.
Faz 4: VLM Entegrasyonu (Yapay Zeka Beyni)
Görüntü ve sesin birleştiği nokta.
•	Filtrelenmiş görseli ve o saniyeye ait Whisper transcript'ini modele gönder.
•	Prompt: "Bu bir teknik video karesidir. Görseldeki kod/şema budur. Konuşmacı da o an şunu söylemiştir: [Transcript]. Bu iki veriyi birleştirip bağlamı JSON olarak özetle."
•	Dönen özeti all-MiniLM-L6-v2 ile embedding'e (sayısal diziye) çevirip veritabanına kaydet.
Faz 5: MCP Sunucusu (Ajan Köprüsü)
•	Python MCP SDK ile sunucu oluştur. İki temel araç (tool) yaz:
1.	semantic_visual_search(query): Kullanıcının metnini embedding'e çevirip SQLite'ta vektör araması yapar ve en benzer video anlarını, özetleriyle birlikte döndürür.
2.	get_frame_context(video_name, timestamp): Cursor istediğinde o saniyenin tam OCR, ses ve özet verisini detaylı getirir.
4. Kritik Mühendislik Uyarıları
•	Asenkron Mimari (Hayat Memat Meselesi): OpenCV, Whisper, OCR ve VLM... Bunların hiçbiri aynı anda, aynı döngü içinde ("while frame:" altında) çalışmamalıdır. OpenCV ve FFmpeg veriyi üretip klasöre bırakır (Producer). Arka planda çalışan asenkron işçiler (Consumer) bu dosyaları sırayla alıp okur ve veritabanına yazar. Aksi takdirde video oynatıcı kilitlenir.
•	Embedding Boyutları: Vektör arama için devasa modeller kullanma. Görevin sadece cümlenin anlamını yakalamak. sentence-transformers kütüphanesindeki en hafif modeller işini fazlasıyla görecektir.
•	Vibe Coding Yönlendirmesi: Yapay zekaya kod yazdırırken modülleri tamamen izole iste. Örnek: "Bana sadece bir klasördeki resimleri izleyen ve bunlara sırayla EasyOCR uygulayıp JSON çıktısı veren bağımsız bir Python scripti yaz."
Geliştirme Sürecindeki Riskler (Eksiler ve Darboğazlar)
Bir mühendis olarak bu projede şu noktalarda başın ağrıyacak, hazırlıklı olmalısın:
•	Orkestrasyon Zorluğu: Elinde birbirini bekleyen çok fazla asenkron parça var. OpenCV resmi kaydetti, ffmpeg sesi çıkardı, OCR metni okudu, Whisper sesi yazıya döktü... Peki bunlardan biri hata verirse ne olacak? Ses dökümü başarıyla bitip OCR çökerse, VLM'e eksik veri mi gidecek? Bu "state" (durum) yönetimini sağlamak için sağlam bir hata yakalama (try-catch) ve loglama mekanizması kurman şart.
•	Veri Şişkinliği (Storage Bloat): Her filtrelenmiş kareyi output_frames/ içine kaydetmek, uzun vadede diski dolduracaktır. İşlemi biten, embedding'i çıkarılan resimleri silen (veya sadece metnini tutup resim dosyasını uçuran) bir "Garbage Collector" (çöp toplayıcı) mantığı eklemen gerekecek.
•	Vibe Coding Tuzağı: LLM asistanlarıyla kod yazarken, modüllerin (vision, database, agent) birbiriyle konuşma arayüzlerini (Interface) baştan çok katı belirlemezsen, projenin ortasında kodlar spagettiye dönebilir. Asistanlara her modülü tamamen bağımsızmış gibi yazdırmalı ve birleştirme işini sen yönetmelisin.
1. Orkestrasyon ve Durum Yönetimi (State Management)
Asenkron görevleri yönetmek için Kafka veya RabbitMQ gibi ağır araçlara ihtiyacın yok. Halihazırda hafıza merkezi için kullanacağın SQLite'ı bir "İş Kuyruğu" (Job Queue) olarak kurgulamak en temiz çözümdür.
•	Job (Görev) Tablosu: Veritabanında ana tabloların haricinde bir processing_queue tablosu oluştur.
•	Durum (Status) Takibi: OpenCV yeni bir kare yakaladığında bu tabloya bir satır ekler. Sütunlar şöyle olmalıdır: frame_id, ocr_status, audio_status, vlm_status.
•	State Makinesi: Her işlem kendi sütununu günceller (PENDING -> PROCESSING -> COMPLETED veya FAILED).
•	Hata Toleransı (Try-Catch): Eğer OCR çökerse, ilgili satırın ocr_status değeri FAILED olarak güncellenir. Ajan (VLM) sadece ocr_status == 'COMPLETED' ve audio_status == 'COMPLETED' olan satırları işleme alır. Böylece sistem eksik veriyle özet çıkarmaya çalışmaz ve kilitlenmez.
2. Veri Şişkinliğini Önleme (Garbage Collector)
Görsel ve ses dosyaları sadece VLM'e bağlam (context) sağlamak için anlık olarak lazımdır. Anlam çıkarıldıktan sonra ham dosyalara ihtiyacın kalmaz.
•	Tetikleyici Mantığı: processing_queue tablosunda bir karenin (veya ses parçasının) vlm_status değeri COMPLETED olduğunda, bu verinin metin özeti ve vektörü ana veritabanına başarıyla kaydedilmiş demektir.
•	Silici İşçi (Cleaner Worker): Arka planda her 5 dakikada bir uyanan çok hafif bir Python betiği çalıştır. Bu betik, durumu COMPLETED olan tüm dosyaların diskteki dosya yollarını (path) bulup os.remove() ile silsin.
•	Debug Modu: Geliştirme aşamasında "Bu özet neden yanlış çıktı?" diye kontrol etmen gerekeceği için bir .env dosyasına KEEP_RAW_FILES=True ayarı koy. Canlı kullanıma geçtiğinde bunu False yaparsın.

1. Test Yazımı (Unit ve Integration Tests)
Sektörde kod yazıldıktan sonra değil, kodla birlikte test yazılır. Sistemin her parçası bağımsız olarak test edilmelidir.
•	Biz Nasıl Yapacağız? Kodlama bittiğinde (veya modül modül ilerlerken) pytest kütüphanesini kullanacağız. Endişelenme, testleri manuel yazıp saatlerini harcamayacaksın. "Vibe coding" stratejimiz burada çok işe yarayacak. LLM'e "Şu yazdığın worker.py dosyası için %80 kapsama (coverage) sahip bir pytest dosyası üret" diyeceğiz.
•	Örneğin; OpenCV'nin resmi doğru kırpıp kırpmadığını veya Whisper'ın sesi doğru alıp almadığını yapay zeka ajanının yazdığı sahte verilerle (mock data) otomatik test edeceğiz.
2. Bağımlılık Yönetimi (Dependency Management)
Sektörde kimse pip install -r requirements.txt yapıp geçmez. Çünkü senin bilgisayarındaki kütüphane sürümleriyle, projeyi indirecek başka bir mühendisin sürümleri çakışabilir.
•	Biz Nasıl Yapacağız? Sektör standartı olan pyproject.toml (Poetry veya uv gibi modern araçlarla) kullanacağız. Böylece projenin hangi Python sürümünde, hangi kütüphanenin tam olarak hangi versiyonuyla çalıştığı mühürlenmiş olacak.
3. Docker (Konteynerizasyon) Konusu
Docker, yazdığın kodun, veritabanının ve işletim sisteminin minyatür bir kopyasını alıp kapalı bir kutu (container) içine koyar. Böylece kod her bilgisayarda aynı şekilde çalışır. "Docker bilmiyorum" diye hiç çekinme; vibe coding ile bir Dockerfile ve docker-compose.yml yazdırmak en kolay işlerden biridir. Ancak bu projede stratejik bir karar vermemiz gerekecek:
•	Yaptığın sistem bir web sitesi değil, geliştiricinin bilgisayarında (lokalde) çalışıp, onun dosyalarını ve IDE'sini izleyecek bir Model Context Protocol (MCP) sunucusu.
•	Uygulamayı Docker içine hapsetmek, onun senin bilgisayarındaki videolara ve IDE dosyalarına erişmesini zorlaştırabilir (yetki ve dosya yolu sorunları çıkar).
•	Bizim Stratejimiz: Sistemin çekirdek kodunu (MCP, OpenCV) standart bir Python paketi olarak bırakacağız. Ancak sistemi yoran yerel VLM veya veritabanı (SQLite VSS) gibi bileşenleri ayağa kaldırmak için tek tıklamayla çalışan bir docker-compose.yml dosyası hazırlatacağız. Sektörde yerel geliştirici araçları tam olarak bu şekilde hibrit (melez) paketlenir.
4. Sürekli Entegrasyon (CI/CD - GitHub Actions)
Sektördeki mühendisler kodu GitHub'a gönderdiklerinde (Push), arka planda bir robot uyanır. Kodun formatını (Linting) kontrol eder, yazdığımız testleri çalıştırır ve "Bu kod bozuk, ana projeye eklenemez" ya da "Her şey mükemmel, onaylandı" der.
•	Biz Nasıl Yapacağız? Proje klasörüne .github/workflows/ adında bir dosya açacağız. Claude/Cursor'a "Bu projede her push atıldığında pytest'leri çalıştıran bir GitHub Actions YAML dosyası yaz" diyerek bu sistemi saniyeler içinde kuracağız.
Çapraz Platform (Windows/Linux/macOS) Desteği
Adım 1: Mimari ve İsterlerin Belirlenmesi (Requirements & Architecture)
•	Problem ne? (Videoların akıp gitmesi).
•	Çözüm ne? (VLM tabanlı asenkron özetleyici).
•	Biz bunu manifestoyu hazırlayarak başardık.
Adım 2: Veri Modelleme (Data Modeling - Şu an bulunduğumuz adım)
•	Hangi veriler tutulacak? Şemalar nasıl olacak?
•	Veritabanı (SQLite) ayağa kaldırılır, tablolar oluşturulur.
Adım 3: Sahte Verilerle Çekirdek Mantık (Mocking & Core Logic)
•	Profesyoneller hemen OpenCV'yi bağlayıp ağır videolarla test yapmazlar.
•	Kuyruğa elle 3-4 tane "sahte" (mock) veri eklenir. Worker (İşçi) modülünün bu sahte verileri alıp almadığı, çöküp çökmediği test edilir.
Adım 4: Parçaların Entegrasyonu (Integration)
•	Veritabanı ve kuyruk tıkır tıkır çalışıyorsa, gerçek OpenCV modülü yazılır ve sisteme bağlanır.
•	Ardından Whisper ve EasyOCR bağlanır.
•	En son VLM bağlanarak anlamsal veri elde edilir.
Adım 5: Dış Dünyaya Açılış (API / MCP Server)
•	Tüm sistem içeride kusursuz çalıştıktan sonra, bunu Cursor veya Claude'un okuyabileceği MCP (Model Context Protocol) formatına çevirecek sunucu katmanı yazılır.
Adım 6: Paketleme ve CI/CD (Deployment)
•	Testler (pytest) yazılır.
•	Bağımlılıklar kilitlenir (pyproject.toml).
•	Çapraz platform kurulum scriptleri ve GitHub Actions süreçleri eklenir.
1. Neler Yaptık? (Tamamlanan Fazlar)
•	Faz 1 (Görsel Hafıza): frame_extractor.py ile videoyu anlamlı karelere (keyframes) ayırdık, EasyOCR ile metinleri okuduk.
•	Faz 2 (İşitsel Hafıza): audio_processor.py ile videodaki sesi ayırıp Whisper kullanarak zaman damgalı metin dökümleri (transcript) elde ettik.
•	Faz 3 (Zeka/Anlamlandırma): sentence-transformers (all-MiniLM-L6-v2) ile bu metinleri "anlamsal vektörlere" dönüştürüp SQLite veritabanına kaydeden yapıyı kurduk.
•	Faz 4 (Orkestrasyon): worker.py ile tüm bu süreçleri birbirine bağlayan "Zeki İşçi"yi başlattık. İşçi şu an Görüntü + OCR + Ses üçlüsünü tek bir karede birleştirip veritabanına işliyor.
2. Neredeyiz? (Testin Durumu)
En son yaptığımız uçtan uca testte:
•	Sistem Akışı: Başarılı. (Video kareleri işleniyor, konuşmalar yakalanıyor, veritabanına vektör olarak kaydediliyor).
•	Kritik Hata: VLM (Ollama) ile metin özetleme aşamasında 500 Server Error alıyoruz.
3. Neler Kaldı?
•	Model Motoru Ayarı: Ollama'yı güncelleyip modeli "konuşturmak".
•	Prompt Optimizasyonu (İnce Ayar): VLM çalışmaya başladığında, "Özet çok kısa/yüzeysel" dersen, ona daha teknik bir dil kullanması için "Prompt Mühendisliği" yapacağız.
•	Faz 5 (Final): MCP Sunucusu. (Senin bu projeyi Claude veya Cursor gibi araçlara "bağlayıp" sorular sormanı sağlayacak olan köprü).

