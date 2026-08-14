# Ekran görüntüleri

**Son güncelleme:** 15 Ağustos 2026, 01:28

Claude'a göstermek istediğin her görsel buraya atılır. Sonra sohbette
**"ss'e yeni görsel attım"** demen yeterli — Claude bu klasöre bakar.

## Kural

- Dosya adı **ne olduğunu söylesin**: `qgc_hud_kalkis.png`, `yki_failsafe.png`,
  `harita_5nokta.png`. `Screenshot 2026-08-14 at 20.13.44.png` işe yaramaz —
  Claude hangisine bakacağını bilemez, sen de bir hafta sonra bilemezsin.
- İşi biten görselleri sil. Bu klasör arşiv değil, **pano**.
- Görseller git'e **girmiyor** (`.gitignore`). Kalıcı olması gereken bir kanıt
  varsa (uçuş kanıtı ekran görüntüsü gibi) `docs/` altına, adıyla koy.

## Ne işe yarar

Claude terminal çıktısını okuyabilir ama şunları okuyamaz:
- QGroundControl HUD'u, PX4 parametre ekranı, kalibrasyon sihirbazı
- YKİ arayüzünün görünümü (uyarı kutuları, harita, drone kartları)
- Osiloskop / analizör ekranı, fiziksel kablo düzeni, hasar fotoğrafı

Bunları gördüğünde teşhis tahminden ölçüme döner.
