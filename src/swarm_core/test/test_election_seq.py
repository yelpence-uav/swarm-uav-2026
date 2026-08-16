# Copyright 2026 Yelpence
"""election.seq_kabul: eskimis ElectionResult filtresi.

30 Temmuz'da olculen ariza: tek global `max_seen_seq` yuzunden yeniden baslayan
(ya da yeni secilen) liderin butun secim sonuclari SESSIZCE dusuyordu. Iki
kollu saha deneyi:
    seq=100 round=5 -> kabul  (log cikti)
    seq=5   round=9 -> RED    (round YUKSEK oldugu halde; tek engel seq)
Bu testler duzeltmenin o davranisi tersine cevirdigini ve eski dogru
davranisin (ayni yayincidan gelen gercek eskimis mesaji atmak) korundugunu
sabitler.
"""

from swarm_core.consensus import election


def test_ilk_mesaj_kabul():
    """Hic gorulmemis kaynaktan gelen ilk mesaj kabul edilir."""
    kabul, degisti = election.seq_kabul({}, kaynak=1, incarnation=7, seq=1)
    assert kabul is True
    assert degisti is False


def test_ayni_incarnation_eskimis_mesaj_reddedilir():
    """Ayni yayincidan gelen gerçek eskimis mesaj hala atilir."""
    seen = {1: (7, 100)}
    assert election.seq_kabul(seen, 1, 7, 100)[0] is False   # esit
    assert election.seq_kabul(seen, 1, 7, 5)[0] is False     # kucuk
    assert election.seq_kabul(seen, 1, 7, 101)[0] is True    # buyuk


def test_incarnation_degisince_dusuk_seq_kabul():
    """ASIL DUZELTME: yayinci yeniden baslarsa seq=1 bile kabul edilir.

    Saha deneyindeki B kolu tam olarak buydu ve reddediliyordu.
    """
    seen = {1: (7, 100)}
    kabul, degisti = election.seq_kabul(seen, 1, incarnation=999, seq=1)
    assert kabul is True
    assert degisti is True


def test_kaynak_basina_ayri_sayac():
    """Lider el degistirince yeni liderin seq=1'i dusmez.

    Global sayacta agent 3'un seq=1'i, agent 1'in seq=100'u yuzunden
    reddedilirdi. Lider devri NORMAL bir islem oldugu icin bu daha sinsiydi.
    """
    seen = {1: (7, 100)}
    assert election.seq_kabul(seen, kaynak=3, incarnation=42, seq=1)[0] is True


def test_incarnation_sifir_eski_gonderici():
    """incarnation=0 (bilinmiyor) ayni kaynakta tutarli davranir.

    Eski surum gonderici hep 0 verir; o durumda filtre eski gibi calisir -
    yani kaynak basina seq karsilastirmasi. Sessizce her mesaji kabul edip
    tekrar oynatma (replay) acigi yaratmamali.
    """
    seen = {1: (0, 50)}
    assert election.seq_kabul(seen, 1, 0, 40)[0] is False
    assert election.seq_kabul(seen, 1, 0, 51)[0] is True


def test_sozluk_degistirilmez():
    """seq_kabul saf: verilen sozlugu DEGISTIRMEZ (guncelleme cagiranda)."""
    seen = {1: (7, 100)}
    kopya = dict(seen)
    election.seq_kabul(seen, 1, 999, 1)
    election.seq_kabul(seen, 5, 3, 9)
    assert seen == kopya
