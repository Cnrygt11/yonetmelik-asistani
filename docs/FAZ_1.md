# Faz 1 · Derlem (2–3. haftalar)

Plan bölüm 13: envanter, edinme, metin çıkarma, P1 belgelerin güncel metinlerinin hazırlanması.
**Çıktı:** derlem v1 ve manifest. **Çıkış ölçütü (M1):** P1 belgelerin tamamı doğrulandı.

## Karar K-09 · İşlenmiş metin KAYSİS'ten alınır

Elle konsolidasyon (plan 6.3) yerine işlenmiş metin doğrudan KAYSİS'ten alınır. Güncellik,
elle karşılaştırma yerine üç otomatik kontrolle doğrulanır:

1. **Resmî Gazete tablosu:** İşlenmiş PDF'lerin sonundaki yayım/değişiklik tablosu manifest'le
   karşılaştırılır. Tablodaki her değişikliğin metinde en az bir notu bulunmalıdır.
2. **İlk yayım nüshası:** KAYSİS bazı yönetmelikleri işlenmemiş Resmî Gazete nüshası olarak
   verir. Bunlar için değişiklik olmadığı başka bir kaynakla teyit edilip manifest'e yazılır
   (`degisiklik_teyidi`). Teyit bir dönemden eskiyse kontrol başarısız olur.
3. **Çapraz kaynak:** İkinci kaynağı olan belgeler (mevzuat.gov.tr) madde madde karşılaştırılır.

Neden: Ön araştırmada 2023 değişikliği (RG 32125) gözden kaçmıştı. Elle konsolidasyon tam bu
türden hatalar üretir; iki bağımsız resmî kaynağın metni ise birebir karşılaştırılabilir.

## Komutlar

```bash
uv sync --extra ingest
python -m yonetmelik_asistani.ingest index        # KAYSİS listesi; önceki listeye göre farklar
python -m yonetmelik_asistani.ingest download     # P1 (veya --oncelik P1,P2 / --id <belge>)
python -m yonetmelik_asistani.ingest extract      # metin + güncellik kontrolü (sorun varsa çıkış 1)
python -m yonetmelik_asistani.ingest crosscheck   # ikinci kaynakla madde madde karşılaştırma
```

## Kontrol listesi

### Envanter
- [x] KAYSİS listesi çıkarıldı: 545 belge, öğrencileri ilgilendiren ~40 belge manifest'e alındı
- [x] Taslak manifest düzeltildi: 2023 değişikliği eklendi; ayrı bir "Yatay Geçiş Yönergesi"
      yok (hükümler Geçiş/ÇAP/Yan Dal yönergesinde); Muafiyet ve İntibak Yönergesi eklendi
- [x] 2018 öncesi adla ("Uludağ Üniversitesi") duran 9 belge `inceleme` durumunda; yürürlüğü
      teyit edilmeden indekslenmez

### Edinme ve metin çıkarma
- [x] KAYSİS istemcisi: eksik TLS ara sertifikası depoda (`certs/`, son geçerlilik 02.11.2027),
      ASP.NET çerez yönlendirmesi çözüldü
- [x] mevzuat.gov.tr desteği (2547 sayılı Kanun ve çapraz kontrol)
- [x] Satır yapısı onarımı: kelime kelime bölünmüş satırlar, sayfa sonu başlıkları, sayfa geçişinde
      devam eden cümleler; kanun biçimi ("Madde 54 –", "a.")
- [x] İndirilen dosyaların özeti `configs/corpus_lock.json`'da

### P1 doğrulama · 12.10.2026
| Belge | Biçim | Madde | Güncellik | Çapraz kontrol |
|---|---|---|---|---|
| Önlisans ve Lisans Eğitim Öğretim Yönetmeliği | işlenmiş | 50 | 2 değişiklik, notlar tam | mevzuat.gov.tr 50/50 aynı |
| Yaz Öğretimi Yönetmeliği | ilk yayım nüshası | 17 | değişiklik yok (mevzuat.gov.tr) | mevzuat.gov.tr 17/17 aynı |
| YDYO Yabancı Dil Yönetmeliği | mevzuat.gov.tr (34783), 3 tablo | 37 | değişiklik yok (mevzuat.gov.tr, Lexpera) | KAYSİS 36/37 aynı + 1 bilinen fark |
| Geçiş, ÇAP, Yan Dal, Kredi Transferi Yönergesi | yönerge | 34 | KAYSİS | — |
| Muafiyet ve İntibak Yönergesi | yönerge | 12 | KAYSİS | — |
| 2547 sayılı Kanun | işlenmiş (mevzuat.gov.tr) | 229 | 7437 değişikliği ve AYM iptali metinde (zorunlu ifade) | — |

- [x] P1 belgelerin tamamı `extract` kontrolünden geçti
- [x] YDYO yönetmeliğinin mevzuat.gov.tr numarası bulundu (34783) ve çapraz kontrole eklendi
- [x] AYM'nin 22.02.2024 tarihli kararı (E: 2023/78, K: 2024/55) md. 54'e işlenmiş: 1-a(3), b(7),
      d(2) alt bentleri ve f bendi iptal notlu. `zorunlu_ifadeler` ile kalıcı kontrol altında.
- [x] **M1 tamamlandı (12.10.2026) → Faz 2: parçalama ve indeks**

## Bulgular ve Faz 2'ye aktarılanlar

- **Resim olarak gömülü tablolar:** KAYSİS'teki YDYO nüshasında hazırlık muafiyeti için eşdeğer
  sınav puanları ve harf notu tabloları resimdi; metin çıkarımında sessizce kayboluyordu. Çapraz
  kontrol yakaladı. Birincil kaynak mevzuat.gov.tr yapıldı; artık resim içeren her sayfa için
  `extract` uyarı veriyor.
- **Tablolar Markdown'a çevriliyor** (plan 6.4). Faz 2'de tablo satırları bölünmeyecek; tablo,
  içinde bulunduğu fıkrayla tek parça tutulacak.
- **2547 md. 54 çok uzun** (~17.000 karakter, 98 satır). Faz 2'de fıkra/bent düzeyinde parçalanmalı.
- **Kanunun başında künye, sonunda "işlenemeyen hükümler" tabloları var**; Faz 2'de yalnızca
  `maddeler: [44, 54]` kullanılacak.
- **Colab:** `data/` Git dışında. Faz 2'nin Colab'daki ilk adımı `download` + `extract` olacak.
