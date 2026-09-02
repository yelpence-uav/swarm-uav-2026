from swarm_control.esp32_bridge import packet_parser as pp

TABLO = [(1, 38.6910000, 39.1615000), (2, 38.6912500, 39.1618000),
         (3, 38.6915000, 39.1621000), (4, 38.6917500, 39.1624000),
         (5, 38.6920000, 39.1627000)]
N = len(TABLO)

# --- GONDEREN (baz): her QR ayri cerceve ---
cerceveler = [pp.qr_koord_paketle(qid, N, la, lo) for qid, la, lo in TABLO]
print(f"gonderen: {len(cerceveler)} cerceve, her biri {len(cerceveler[0])} bayt")

def topla(gelen):
    """_isle_qr_coords ile ayni mantik."""
    toplayici, toplam = {}, 0
    for c in gelen:
        q = pp.qr_koord_coz(c)
        toplam = q.toplam
        toplayici[q.qr_id] = (q.lat, q.lon)
        if toplam > 0 and len(toplayici) >= toplam:
            return sorted(toplayici.items())
    return None

# 1) Tam iletim
r = topla(cerceveler)
ok1 = r is not None and len(r) == N
hata = 0
if ok1:
    for (qid, (lat, lon)), (oqid, ola, olo) in zip(r, TABLO):
        if qid != oqid or abs(lat/1e7-ola) > 1e-7 or abs(lon/1e7-olo) > 1e-7:
            hata += 1
print(f"  {'OK  ' if ok1 and not hata else 'HATA'} tam iletim -> tablo tamamlandi, {N} nokta, degerler birebir")

# 2) Bir cerceve DUSERSE tablo tamamlanmamali (dokumante davranis)
r2 = topla(cerceveler[:-1])
print(f"  {'OK  ' if r2 is None else 'HATA'} 1 paket kaybi -> tablo tamamlanMAZ (bu yuzden 4 kopyali tekrar var)")

# 3) Sinir denetimleri sessiz kirpmiyor mu
for kotu, ad in [((1, N, 91.0, 39.0), 'enlem 91'), ((1, N, 38.0, 181.0), 'boylam 181'),
                 ((300, N, 38.0, 39.0), 'qr_id 300')]:
    try:
        pp.qr_koord_paketle(*kotu); print(f"  HATA {ad} kabul edildi (sessiz kirpma!)")
    except ValueError:
        print(f"  OK   {ad} REDDEDILDI (ValueError)")
