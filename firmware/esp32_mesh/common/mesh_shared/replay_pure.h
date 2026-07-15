#pragma once
// ===== ANTI-REPLAY — ARDUINO'DAN BAGIMSIZ SAF KARAR MANTIGI (F1) =====
// rtk_pure.h ile ayni felsefe: guvenlik kritik KARAR burada, tek yerde,
// Arduino/NVS/Serial'den bagimsiz yasar ve native'de (ASan/UBSan ile) test
// edilir. mesh_config.h yalnizca ince bir kabuk: loglar ve NVS'e yazar.
//
// F1 KURALI (session_id artik gonderici basina MONOTON — bkz mesh_config.h::
// _session_id_uret(), NVS boot sayaci):
//   gelen_session  <  bilinen  -> RED (eski session = reboot-replay saldirisi)
//   gelen_session  == bilinen  -> normal sliding-window mantigi
//   gelen_session  >  bilinen  -> gonderici reboot etti, kabul + pencere sifirla
//
// "bilinen": once RAM (replay_state_t), RAM yoksa (ilk paket) NVS'teki
// kalici peer kaydi. Alici yarisinin persist edilmesi SART — aksi halde
// saldiri "aliciyi reboot ettir, eski session'i oynat"a kayar.

#include <stdint.h>
#include <string.h>

#define PENCERE_BOYU 64

// Sifreli payload'in ilk 6 byte'i — tel formati, DEGISTIRME (zarf butcesi
// mesh_paket_t.sifreli_veri[24] = anti_replay(6) + payload(18)).
struct
#if defined(__GNUC__)
__attribute__((packed))
#endif
anti_replay_t {
    uint16_t session_id; // gonderici basina monoton (NVS boot sayaci)
    uint32_t paket_id;   // sifrelenmis payload icinde — baslik manipulasyonu engellenir
};

struct replay_state_t {
    uint16_t session_id;
    uint32_t en_yuksek_id;
    uint64_t pencere_bitmask; // son 64 paketin gelis durumu
    bool     ilk_paket;       // true: ilk pakette pencereyi baslatir
};

typedef enum {
    REPLAY_KABUL = 0,           // normal paket, pencere guncellendi
    REPLAY_KABUL_YENI_SESSION,  // daha buyuk session -> pencere sifirlandi, PERSIST ET
    REPLAY_RED_ESKI_SESSION,    // session geriye gitti = replay
    REPLAY_RED_ESKI_PAKET,      // pencerenin disinda kalacak kadar eski
    REPLAY_RED_DUPLIKAT,        // bu paket_id zaten goruldu
} replay_sonuc_t;

// kalici_session: NVS'teki son bilinen session_id (0 = kayit yok).
// Yalnizca rs->ilk_paket iken anlamlidir (RAM durumu yokken tek savunma odur).
static inline replay_sonuc_t replay_karar(replay_state_t* rs,
                                          uint16_t session_id, uint32_t paket_id,
                                          uint16_t kalici_session) {
    if (rs->ilk_paket) {
        // RAM durumu yok (boot, ya da node tablodan dusmus). Kalici kayit
        // varsa eski session'i BURADA yakalamak zorundayiz.
        if (kalici_session != 0 && session_id < kalici_session)
            return REPLAY_RED_ESKI_SESSION;
        rs->session_id      = session_id;
        rs->en_yuksek_id    = paket_id;
        rs->pencere_bitmask = 1ULL;
        rs->ilk_paket       = false;
        // Kalici kayit yoksa ya da degistiyse cagiran taraf persist etmeli.
        return (kalici_session == session_id) ? REPLAY_KABUL
                                              : REPLAY_KABUL_YENI_SESSION;
    }

    if (session_id != rs->session_id) {
        if (session_id < rs->session_id)
            return REPLAY_RED_ESKI_SESSION;   // geriye gidis = replay
        // Daha buyuk session: gonderici reboot etti
        rs->session_id      = session_id;
        rs->en_yuksek_id    = paket_id;
        rs->pencere_bitmask = 1ULL;
        return REPLAY_KABUL_YENI_SESSION;
    }

    // Ayni session — klasik sliding window
    if (paket_id > rs->en_yuksek_id) {
        uint32_t ilerleme   = paket_id - rs->en_yuksek_id;
        rs->pencere_bitmask = (ilerleme >= PENCERE_BOYU)
                              ? 0ULL : (rs->pencere_bitmask << ilerleme);
        rs->pencere_bitmask |= 1ULL;
        rs->en_yuksek_id    = paket_id;
        return REPLAY_KABUL;
    }
    uint32_t fark = rs->en_yuksek_id - paket_id;
    if (fark >= PENCERE_BOYU)                 return REPLAY_RED_ESKI_PAKET;
    if (rs->pencere_bitmask & (1ULL << fark)) return REPLAY_RED_DUPLIKAT;
    rs->pencere_bitmask |= (1ULL << fark);
    return REPLAY_KABUL;
}

// Kabul mu? (cagiran tarafin kisayolu)
static inline bool replay_kabul_mu(replay_sonuc_t s) {
    return s == REPLAY_KABUL || s == REPLAY_KABUL_YENI_SESSION;
}
