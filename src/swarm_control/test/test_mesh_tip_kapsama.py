"""test_mesh_tip_kapsama.py - mesh TIP'lerinin firmware geçitlerinde kapsanması.

NEDEN BU TEST VAR
Saha günlüğü §1.1: `TIP_RTK` RX BASE whitelist'inde olmadığı için her RTCM
çerçevesi "tanınmayan tip sessizce atılır" dalına düşüyordu ve **hata sayacı
bile artmıyordu**. Bu kusur sınıfının özelliği çalışma zamanında HİÇBİR sinyal
üretmemesi: paket mesh'i geçer, ESP'ye varır, orada ölür. Ne log, ne sayaç.

Firmware'de DÖRT ayrı geçit var ve her yeni tip için dördü ayrı ayrı
değerlendirilmeli:

    TX DRONE  mesh -> RPi   (alma)      : takipçinin Pi'sine ulaşması için
    TX DRONE  RPi  -> mesh  (gönderme)  : liderin Pi'sinden çıkması için
    RX BASE   mesh -> YKİ   (alma)      : YKİ'nin görmesi için
    RX BASE   YKİ  -> mesh  (gönderme)  : YKİ'nin yayınlaması için

Bu test hem VARLIĞI hem de BİLİNÇLİ YOKLUĞU doğrular. Bir tipi bilerek dışarıda
bıraktıysak burada yazılı; biri onu eklerse test patlar ve gerekçeyi güncellemek
zorunda kalır. Tersi de geçerli: whitelist'ten bir tip düşerse test patlar.

Pi'lerde `firmware/` dizini yok (yalnız ROS paketleri kopyalanıyor), o yüzden
firmware bulunamazsa test atlanır.
"""

import pathlib
import re

import pytest

from swarm_control.esp32_bridge import packet_parser as pp


def _repo_koku() -> pathlib.Path | None:
    """Test dosyasından yukarı çıkıp `firmware/` içeren dizini bulur."""
    for ata in pathlib.Path(__file__).resolve().parents:
        if (ata / 'firmware' / 'esp32_mesh').is_dir():
            return ata
    return None


_KOK = _repo_koku()
_ATLA = pytest.mark.skipif(
    _KOK is None,
    reason='firmware/ bu ortamda yok (Pi kurulumunda yalnız ROS paketleri var)',
)


def _yorumsuz(metin: str) -> str:
    """// ve /* */ yorumlarını atar — yorumdaki TIP adı kod sayılmasın."""
    metin = re.sub(r'/\*.*?\*/', '', metin, flags=re.S)
    return re.sub(r'//[^\n]*', '', metin)


def _blok(dosya: str, bas: str, son: str) -> str:
    """İki işaret arasındaki KOD bloğunu döndürür (yorumlar atılmış).

    İşaretler bulunamazsa testi hata ile düşürür: geçit yapısı değişmişse
    sessizce "her şey yolunda" demek yerine yeniden gözden geçirilmeli.
    """
    src = _yorumsuz((_KOK / dosya).read_text(encoding='utf-8'))
    i = src.find(bas)
    assert i >= 0, f'{dosya}: "{bas}" bulunamadı — geçit yapısı değişmiş olabilir'
    j = src.find(son, i)
    assert j > i, f'{dosya}: "{son}" bulunamadı — geçit yapısı değişmiş olabilir'
    return src[i:j]


# (blok adı, dosya, başlangıç işareti, bitiş işareti)
_GECITLER = {
    'tx_alma': (
        'firmware/esp32_mesh/TX DRONE/src/main.cpp',
        'uint8_t uzunluk = 0;', 'uart_gonder(p->tip',
    ),
    'tx_gonderme': (
        'firmware/esp32_mesh/TX DRONE/src/main.cpp',
        'const bool izinli', 'mesh_tip_gecebilir',
    ),
    'rx_alma': (
        'firmware/esp32_mesh/RX BASE/src/main.cpp',
        'uart_mesaj_t msg = {};', 'memcpy(msg.payload',
    ),
    'rx_gonderme': (
        'firmware/esp32_mesh/RX BASE/src/main.cpp',
        'if (tip_byte == TIP_KOMUT) {', 'uart_gonder(0xFD',
    ),
}

# Sürü koordinasyonu tipleri: hangi geçitte OLMALI, hangisinde OLMAMALI.
# Gerekçeler docs/MESH_PROTOKOL_KARARLARI.md Adım 2'de.
_BEKLENEN = {
    'TIP_FORMASYON':       {'tx_alma', 'tx_gonderme'},
    'TIP_FORMASYON_DEVAM': {'tx_alma', 'tx_gonderme'},
    'TIP_FORM_OFSET':      {'tx_alma', 'tx_gonderme'},
    'TIP_QR_GOREV':        {'tx_alma', 'tx_gonderme', 'rx_alma'},
    # QR_HAM: dronların Pi'sine iletilmez (hiçbir uçuş kararı okumuyor),
    # YKİ'ye iletilir (şema tahmin olduğu için format teşhisi gerekiyor).
    'TIP_QR_HAM':          {'tx_gonderme', 'rx_alma'},
}


@_ATLA
@pytest.mark.parametrize('tip_adi', sorted(_BEKLENEN))
def test_yeni_tip_dogru_gecitlerde(tip_adi):
    """Her yeni TIP tam olarak beklenen geçitlerde olmalı — fazla da değil."""
    bekleniyor = _BEKLENEN[tip_adi]
    for gecit_adi, (dosya, bas, son) in _GECITLER.items():
        kod = _blok(dosya, bas, son)
        # \b sınırı şart: TIP_FORMASYON, TIP_FORMASYON_DEVAM'ın önekidir.
        var = re.search(rf'\b{tip_adi}\b', kod) is not None
        if gecit_adi in bekleniyor:
            assert var, (
                f'{tip_adi} "{gecit_adi}" geçidinde YOK. Bu geçit onu taşımak '
                f'zorunda; eksikse çerçeve sessizce düşer ve hiçbir sayaç '
                f'artmaz (saha günlüğü §1.1).'
            )
        else:
            assert not var, (
                f'{tip_adi} "{gecit_adi}" geçidine EKLENMİŞ ama beklenmiyor. '
                f'Bilinçli bir karar ise docs/MESH_PROTOKOL_KARARLARI.md '
                f'Adım 2 ve bu testteki _BEKLENEN tablosu güncellenmeli.'
            )


@_ATLA
def test_tip_degerleri_firmware_ile_ayni():
    """packet_parser TIP sabitleri firmware mesh_config.h ile birebir olmalı.

    İki taraf ayrışırsa çerçeve yanlış tiple yorumlanır: en iyi durumda CRC'de
    düşer, en kötü durumda BAŞKA bir tipin payload'ı olarak çözülür.
    """
    cfg = _yorumsuz(
        (_KOK / 'firmware/esp32_mesh/common/mesh_shared/mesh_config.h')
        .read_text(encoding='utf-8')
    )
    fw = {ad: int(deger, 16)
          for ad, deger in re.findall(r'#define\s+(TIP_\w+)\s+(0x[0-9A-Fa-f]+)', cfg)}
    assert fw, 'mesh_config.h içinde TIP_* tanımı bulunamadı'

    for ad, deger in fw.items():
        py = getattr(pp, ad, None)
        if py is None:
            continue          # firmware'de olup Python'un kullanmadığı tip olabilir
        assert py == deger, (
            f'{ad}: firmware 0x{deger:02X}, packet_parser 0x{py:02X} — '
            f'iki taraf AYRIŞMIŞ.'
        )


@_ATLA
def test_hiz_limiti_tablosu_en_buyuk_tipi_kapsiyor():
    """MESH_TIP_TABLO_BOYU en büyük TIP'ten büyük olmalı.

    `mesh_tip_gecebilir()` diziyi TIP ile indeksliyor ve taşarsa fail-closed
    davranıp o tipi KOMPLE reddediyor. static_assert bunu derlemede yakalar,
    bu test derleyici olmadan da yakalar.
    """
    cfg = _yorumsuz(
        (_KOK / 'firmware/esp32_mesh/common/mesh_shared/mesh_config.h')
        .read_text(encoding='utf-8')
    )
    boyut = int(re.search(r'#define\s+MESH_TIP_TABLO_BOYU\s+(\d+)', cfg).group(1))
    tipler = [int(d, 16)
              for _, d in re.findall(r'#define\s+(TIP_\w+)\s+(0x[0-9A-Fa-f]+)', cfg)]
    # TIP_FAILSAFE (0xFA) sentinel; mesh_gonder yolundan geçmiyor, tabloya girmez.
    tipler = [t for t in tipler if t != 0xFA]
    assert max(tipler) < boyut, (
        f'En büyük TIP 0x{max(tipler):02X} ({max(tipler)}) >= '
        f'MESH_TIP_TABLO_BOYU ({boyut}) — o tip hız limitinde KOMPLE reddedilir.'
    )
