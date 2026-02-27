# Yelpençe Sürü İHA Projesi - Katkıda Bulunma Kılavuzu

Yelpençe TEKNOFEST 2026 Sürü İHA projesine hoş geldiniz. Takım içi uyumu sağlamak, kod kalitesini korumak ve güvenli bir geliştirme süreci yürütmek için tüm ekip üyelerinin aşağıdaki kurallara uyması zorunludur.

## 1. Branch Yönetimi ve İsimlendirme Kuralları

Projenin kararlı yapısını korumak adına her geliştirme izole bir dalda yapılmalıdır.

* **Doğrudan Yükleme Yasaktır:** `main` dalına doğrudan `git push` yapmak kesinlikle yasaktır.
* **Yeni Dal Açma:** Her yeni özellik, görev veya hata çözümü için `main` dalından güncel bir kopya alınarak yeni bir branch açılmalıdır.
* **Otomatik Dal Silme:** Bir dal main ile başarılı bir şekilde merge birleştirme edildiğinde, o dal GitHub tarafından otomatik olarak silinecektir. Bu, repo temizliğini sağlamak adına zorunlu bir kuraldır.
* **İsimlendirme Şablonları:** Açacağınız dalın ismi, yapacağınız işin türünü belli etmelidir. Lütfen İngilizce karakterler ve küçük harf kullanın, kelimeleri tire (-) ile ayırın:
  * Yeni görevler ve özellikler için: `feature/gorev-adi` (Örn: `feature/qr-detection`)
  * Hata düzeltmeleri için: `bugfix/hata-adi` (Örn: `bugfix/drone-collision`)
  * Belge ve dokümantasyon güncellemeleri için: `docs/readme-guncellemesi`
  * Acil sistem çökmelerini çözmek için: `hotfix/kod-cokmesi`

## 2. Kodlama Standartları ve Stilleri

Projede yazılan kodların herkes tarafından okunabilir ve standartlara uygun olması gerekir.

* **Python (PEP 8):** Yazdığınız tüm Python kodları PEP 8 standartlarına uymak zorundadır. CI/CD sürecimizde `ament_flake8` aracı bu standartları otomatik olarak denetler. Kurallara uymayan kodlar sisteme kabul edilmez.
* **Girintileme:** Her girinti için 4 boşluk (Tab yerine boşluk) kullanın.
* **Satır Uzunluğu:** Bir satır en fazla 79 karakter olmalıdır.
* **Boş Satırlar:** Fonksiyonlar ve sınıflar arasında iki, sınıf içi metodlar arasında bir boş satır bırakılmalıdır.
* **İsimlendirme:** Fonksiyon ve değişken isimlerinde `snake_case`, Sınıf (Class) isimlerinde `CamelCase` formatı kullanılmalıdır.
* **Belgelendirme (Docstrings):** Yazdığınız sınıfların ve fonksiyonların ne iş yaptığını anlatan yorum satırları (PEP 257) eklenmelidir.
* **Yerel Test:** Kodunuzu GitHub'a göndermeden önce kendi bilgisayarınızda `colcon test` komutu ile test etmeniz beklenmektedir.
* **Referans:** Tüm kuralları öğrenmek ve uygulamak için şu kaynakları baz alınız: [PEP 8 -- Style Guide for Python Code](https://peps.python.org/pep-0008/)

**Yorum Satırları ve Docstring Formatı**
Kodun mantığı sadece kodun kendisinden değil, docstring yapısından da anlaşılmalıdır. Fonksiyonlarda aşağıdaki formatı kullanın:

```python
def calculate_formation_distance(leader_pos, follower_pos):
    """
    İki İHA arasındaki formasyon mesafesini hesaplar.

    Args:
        leader_pos (list): Lider İHA'nın [x, y, z] koordinatları.
        follower_pos (list): Takipçi İHA'nın [x, y, z] koordinatları.

    Returns:
        float: İki İHA arasındaki Öklid mesafesi.
    """
    # Mesafe hesaplama mantığı burada yer alır
    pass
```

## 3. Güvenlik ve CI/CD Süreçleri

Depomuzda kod güvenliğini ve bütünlüğünü koruyan otomatik sistemler bulunmaktadır:

* **Otomatik Kontroller:** Açtığınız her Pull Request (PR) sonrasında GitHub Actions üzerinde ROS 2 derleme testleri ve stil denetimleri otomatik olarak başlar.
* **Bandit Analizi:** Eklenen tüm Python kodları `Bandit` aracı ile güvenlik zafiyetlerine ve mantık hatalarına karşı taranır. Güvenlik testinden geçemeyen kodlar düzeltilene kadar onaylanmaz.
* **Dependabot:** Proje bağımlılıkları Dependabot tarafından otomatik güncellenir. Bu botun açtığı PR'lara takım lideri onayı olmadan müdahale edilmemelidir.
* **Hata Düzeltme Sorumluluğu:** Eğer bir PR bu kontrollerden geçmezse (kırmızı çarpı alması durumunda), hatayı düzeltmek tamamen PR'ı açan kişinin sorumluluğundadır. Takım kaptanı hataları takip etmek veya geliştiriciyi bilgilendirmek zorunda değildir. Kontrolleri takip edin ve tüm testler yeşil (Passed) olana kadar kodunuzu güncelleyin.

## 4. Commit Mesajı Kuralları

Geçmişe dönük kod takibini kolaylaştırmak için `[Tür]: [Kısa Açıklama]` şablonunda "Geleneksel Commit" yapısı kullanılmalıdır.

* `feat: Sürü formasyonu için yeni algoritma eklendi`
* `fix: QR okuyucudaki bellek sızıntısı giderildi`
* `style: GCS arayüzündeki PEP 8 hataları düzeltildi`
* `docs: Kurulum adımları README dosyasına eklendi`

## 5. Pull Request (PR) Oluşturma ve Kod İnceleme

Geliştirmenizi tamamladığınızda kodunuzu ana sisteme entegre etmek için bir PR oluşturmalısınız.

* **PR Açıklaması:** PR başlığı net olmalı, açıklama kısmında yapılan değişiklikler maddeler halinde kısaca yazılmalıdır. Varsa ilgili Issue numarası belirtilmelidir (Örn: `Closes #12`).
* **Review (İnceleme) İsteği:** PR oluşturulduktan sonra sağ taraftaki "Reviewers" kısmından takım liderinden onay (review) talep edilmesi zorunludur.
* **Birleştirme (Merge) Şartı:** Bir PR'ın `main` dalına katılabilmesi için;
  1. Tüm CI/CD ve güvenlik testlerinden yeşil tik (Passed) alması,
  2. Takım lideri tarafından "Approve" (Onay) verilmiş olması gerekmektedir.
* **Merge Yetkisi:** "Merge pull request" butonuna basma yetkisi sadece Takım Kaptanı'na aittir. Testler yeşil olsa dahi, kaptan dışında hiç kimse hiçbir koşulda merge işlemi yapmamalıdır.

## 6. İletişim ve Hata Bildirimi

* Yeni bir özellik geliştirmeye başlamadan veya büyük bir mimari değişiklik yapmadan önce GitHub Issues üzerinden bir konu açın ve ekibi bilgilendirin.
* Karşılaştığınız hataları çözerken veya yeni bir kod yazarken takıldığınız noktalarda takım arkadaşlarınızdan destek istemekten çekinmeyin.
