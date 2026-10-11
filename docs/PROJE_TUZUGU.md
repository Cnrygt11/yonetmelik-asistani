# Proje Tüzüğü · Yönetmelik Asistanı

| | |
|---|---|
| Belge kodu | YA-TZK-01 |
| Sürüm | 1.0 (onaya sunulan taslak) |
| Tarih | 11 Ekim 2026 |
| Dayanak | Proje planı YA-PLN-01, sürüm 1.0 |
| Proje yürütücüsü | [Ad Soyad] |
| Danışman | [Unvan Ad Soyad] |

## 1. Amaç

Bursa Uludağ Üniversitesi öğrencilerinin yönetmelik ve yönergelerle ilgili sorularına,
yürürlükteki metne atıf yapan, doğrulanabilir cevaplar veren açık kaynaklı bir asistan
geliştirmek. Kanıt bulunamadığında sistem tahmin yürütmez; "bulamadım" der ve öğrenciyi
ilgili birime yönlendirir.

## 2. Kapsam

**Kapsamda:** önlisans ve lisans eğitim-öğretim ve sınavlar, yaz öğretimi, hazırlık ve yabancı
dil muafiyeti, yatay geçiş, çift anadal, yan dal, kredi transferi, disiplin hükümleri
(2547 sayılı Kanun md. 54); v1.0 ile lisansüstü eğitim ve birim yönergeleri.

**Kapsam dışında:** öğrencinin kişisel kayıtları (not, devamsızlık durumu, borç), resmî
işlemler, bağlayıcı hukuki görüş, üniversite dışı kurumların kuralları (KYK, ÖSYM),
personel mevzuatı.

## 3. Teslimatlar

| Kilometre taşı | Hafta | Teslimat |
|---|---|---|
| M1 | 3 | Doğrulanmış derlem v1 (P1 belgeler) ve manifest |
| M2 | 5 | İndeks v1, ilk arama ölçümü (Recall@5) |
| M3 | 7 | Uçtan uca çalışan MVP (notebook) |
| M4 | 9 | MVP demosu (arayüz) |
| M5 | 11 | Kilitli test setinde MVP hedefleri |
| M6 | 13 | Pilot raporu |
| M7 | 14 | v1.0, kullanım ve bakım kılavuzları, final raporu |

## 4. Başarı ölçütleri

- Kilitli test setinde ≥ %85 tam doğru cevap ve ≥ %95 doğru atıf
- Cevabı derlemde olmayan soruların ≥ %90'ında doğru ret
- T4 üzerinde tam cevap süresi p95 ≤ 20 sn
- Pilotta SUS ≥ 70 ve "faydalı" oyu ≥ %80

## 5. Roller

| Rol | Kişi / birim | Sorumluluk |
|---|---|---|
| Proje yürütücüsü | [Ad Soyad] | Geliştirme, değerlendirme, dokümantasyon |
| Danışman | [Unvan Ad Soyad] | Faz geçiş onayları, yöntem denetimi |
| Alan uzmanı | Öğrenci İşleri (talep edildi) | Belge listesi ve altın cevap doğrulaması |
| Altyapı | Bilgi İşlem (talep edildi) | Pilot barındırma ve güvenlik incelemesi |
| Uyum | KVKK birimi (talep edildi) | Aydınlatma metni ve kayıt politikası görüşü |

## 6. Varsayımlar ve kısıtlar

- Geliştirme Google Colab ücretsiz katmanında (NVIDIA T4, 16 GB) yapılır; oturum sürekliliği
  garanti değildir. Colab yalnızca geliştirme ve demo için kullanılır.
- Yalnızca açık ağırlıklı ve Apache-2.0 / MIT lisanslı modeller kullanılır.
- Kişisel veri toplanmaz; kullanıcı girişi yoktur.
- Gerçek öğrencilerle pilot, ilgili birimlerin onayı ve KVKK görüşü alındıktan sonra yapılır.
- Alan uzmanının altın seti doğrulamak için 3–6. haftalarda zaman ayırabileceği varsayılır.

## 7. Başlıca riskler

Ayrıntılı tablo planın 14. bölümündedir. En yüksek üç risk: güncel olmayan metnin indekse
girmesi, sayılarda uydurma bilgi ve Colab oturum kesintileri.

## 8. Onay

| | Ad Soyad | Tarih | İmza |
|---|---|---|---|
| Proje yürütücüsü | | | |
| Danışman | | | |
