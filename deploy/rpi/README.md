# RPi Drone Provizyonu (Pi5 / Debian 13)

Taze bir Raspberry Pi 5'i (Debian 13 trixie) sürü drone'una çevirir.
**dd-klon YOK.** Mantık: ortam (ROS+mavros) taşınabilir bir docker image'ıyla,
kod ise host'ta bind-mount ile gelir. Böylece kod değişince image rebuild gerekmez.

> Neden Dockerfile'dan build etmiyoruz? Aktif geliştirmedeyiz; kod image'a gömülü
> olsaydı her değişiklikte Pi'de ~15 dk build gerekirdi.
>
> ⚠️ **16 Ağustos'ta `docker/` komple silindi** (`87e95c2`) — imajın tek tarifi
> oydu. Bugün sorun değil (iki Pi'de imaj hazır), ama **ylp01 dönünce** ve
> **`cv2`+`pyzbar` eklenirken** gerekecek. O zamana kadar tek yol aşağıdaki
> `docker save` yöntemi. Karar `YAPILACAKLAR.md`'ye açılmadı — operatör
> henüz karar vermedi.

## Katmanlar
- **Image `yelpence-ros`** = sadece ORTAM (ROS Jazzy + mavros + geographiclib +
  python venv). Kod İÇİNDE DEĞİL. Referans drone'dan `docker save` ile alınır.
- **Kod** = host'ta `~/yelpence_ws`, konteynere `/ws` olarak mount edilir.
- **Başlatma** = `/ws/baslat.sh` (mavros → px4_bridge → agent_fsm → esp32_bridge).

## Adımlar (yeni drone, örn. agent_id=2)

### 1) Ortam image'ını referans drone'dan al (bir kere)
```bash
# Referans drone'da (ör. ylp00):
docker save yelpence-ros:latest | gzip > yelpence-ros.tar.gz
# Dosyayı yeni drone'a kopyala (scp/rsync).
```

### 2) Host'u hazırla
```bash
# Yeni drone'da:
sudo bash provision_pi.sh
sudo reboot                 # UART overlay + docker grubu için şart
```
`provision_pi.sh` ne yapar: docker.io + socat kurar, kullanıcıyı docker+dialout
gruplarına ekler, `config.txt`'e `dtoverlay=uart4-pi5` ekler (ESP → /dev/ttyAMA4),
docker log limiti koyar. zram + DDS buffer'ları Debian imajında zaten var.

### 3) Ortamı + kodu yükle
```bash
docker load < ~/yelpence-ros.tar.gz          # image
rsync -a <ref>:~/yelpence_ws/ ~/yelpence_ws/  # kod (host'ta)
```

### 4) Konteyneri başlat
```bash
./run_drone.sh 2            # agent_id=2 -> drone2, ns=/drone_2
docker logs -f drone2
```

## Per-drone değişen tek şey: `AGENT_ID`
`run_drone.sh <N>` konteynere `AGENT_ID=<N>` geçer; `baslat.sh` bunu okur
(px4_bridge/agent_fsm/esp32_bridge `agent_id`, mavros ns `/drone_<N>`).
Donanım (ESP/FCU kablolaması) tüm drone'larda aynı → `/dev/ttyAMA0` (FCU) +
`/dev/ttyAMA4` (ESP).

## Faydalı
```bash
docker rm -f drone2            # durdur+sil
docker exec -it drone2 bash    # içine gir
# kod değişince (image'a dokunmadan):
docker exec drone2 bash -lc 'source /opt/ros/jazzy/setup.bash && cd /ws && colcon build --packages-select swarm_control'
```
