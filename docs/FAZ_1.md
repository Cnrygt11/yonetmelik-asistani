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
| YDYO Yabancı Dil Yönetmeliği | ilk yayım nüshası | 37 | değişiklik yok (Lexpera) | — |
| Geçiş, ÇAP, Yan Dal, Kredi Transferi Yönergesi | yönerge | 34 | KAYSİS | — |
| Muafiyet ve İntibak Yönergesi | yönerge | 12 | KAYSİS | — |
| 2547 sayılı Kanun | işlenmiş (mevzuat.gov.tr) | 229 | — | — |

- [x] P1 belgelerin tamamı `extract` kontrolünden geçti
- [ ] YDYO yönetmeliği için mevzuat.gov.tr numarası bulunup çapraz kaynak eklenecek
- [ ] AYM'nin 22.02.2024 tarihli 2547 md. 54 kısmi iptal kararının metne yansıdığı kontrol edilecek
- [ ] **M1 → Faz 2: parçalama ve indeks**
