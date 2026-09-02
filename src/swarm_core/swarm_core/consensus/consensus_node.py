# Copyright 2026 Yelpence
"""Dagitik consensus dugumu: suru lideri arbitrasyonu."""

import random
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    LeaderHeartbeat,
    SystemEvent,
)
from swarm_interfaces.srv import AssignRole

from . import election
from .consensus_context import ConsensusContext
from .consensus_states import ELIGIBLE_STATES

_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# BEST_EFFORT: komşu status'leri proxy'den (/public) BEST_EFFORT geliyor
# (kayıplı kanal). RELIABLE abone best-effort yayıncıyla eşleşmez.
_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_U32 = 2 ** 32


class ConsensusNode(Node):
    """Tek bir drone icin preemptive lider secim dugumu."""

    def __init__(self) -> None:
        super().__init__('consensus_node')

        self._declare_params()

        # incarnation: BU acilisa ozgu kimlik. Alicilar degistigini gorunce
        # bu ajanin sequence_num sayacini sifirlar (bkz. ElectionResult.msg).
        # 0 "bilinmiyor" anlamina ayrildigi icin araliktan cikarildi.
        # SystemRandom kullaniliyor: iki dron ayni anda acilirsa tohumlari
        # ayni olmasin.
        self._incarnation = random.SystemRandom().randrange(1, 0x10000)

        self._ctx = ConsensusContext(
            agent_id=self._agent_id,
            agent_count=self._agent_count,
            stale_s=self._stale_s,
            hb_timeout_s=self._hb_timeout_s,
            battery_min_v=self._battery_min_v,
            grace_s=self._grace_s,
        )
        self._ctx.lider_kilitli = bool(
            self.get_parameter('lider_kilitli').value)
        self._ctx.kilit_tam_kadro_s = float(
            self.get_parameter('lider_kilit_tam_kadro_s').value)
        if self._ctx.lider_kilitli:
            self.get_logger().warning(
                f'[consensus] LIDER KILIDI ACIK (tam kadro bekleme '
                f'{self._ctx.kilit_tam_kadro_s:.1f} sn) — lider bir kez '
                'secilecek ve '
                'DEGISMEYECEK. Lider gercekten duserse devir OLMAZ; '
                'takipciler son formasyon komutunda kalir. Cikis yolu '
                'kill switch. (3 Eylul: liderlik bes kez el degistirip '
                'suruyu bolmustu.)'
            )

        # Liderligi birakma histerezisi (P0.12a): kendi uygunlugumuzu ilk
        # yitirdigimiz an. 0.0 = uygunuz ya da lider degiliz.
        self._uygunsuz_since = 0.0

        self._setup_io()
        self._timer = self.create_timer(1.0 / self._tick_hz, self._tick)

        self.get_logger().info(
            f'ConsensusNode baslatildi: agent_id={self._agent_id} '
            f'incarnation={self._incarnation}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('agent_count', 3)
        self.declare_parameter('tick_hz', 10.0)
        # LIDER KALP ATISI ZAMAN ASIMI — 300 -> 1000 ms (20 Agustos 2026).
        #
        # P0.14(a) ile bu yol ILK KEZ gercekten devreye giriyor; oncesinde
        # `own_airborne` kapisi yuzunden hicbir kararda kullanilmiyordu, yani
        # 300 degeri hic SINANMADI.
        #
        # NEDEN 300 KULLANILAMAZ: kalp atisi 10 Hz ve ESP-NOW broadcast'te
        # kayip ~%30 olculdu. 300 ms = 3 ARDISIK kayip demek; olasiligi
        # 0.3^3 = %2.7 ve 10 Hz'de bu birkac saniyede bir yanlis "lider
        # kayip" uretir — lider yalpasi.
        #
        # 1000 ms = 10 ardisik kayip, 0.3^10 ~ 6e-6: pratikte hic olmaz.
        # Yine de mevcut YEDEK yoldan (3 sn'lik bayatlik) UC KAT hizli.
        #
        # ⚠️ SAYI SAHADA OLCULMEDI. Ilk iki ucakli ucusta kayittan gercek
        # kalp atisi bosluk dagilimina bakilip ayarlanacak — en buyuk boslugu
        # gorup esigi onun ~2 katina koymak dogru yol.
        self.declare_parameter('heartbeat_timeout_ms', 1000.0)
        self.declare_parameter('agent_stale_timeout_s', 3.0)
        self.declare_parameter('battery_min_v', 14.0)
        self.declare_parameter('bootstrap_grace_s', 1.5)
        # P1.14 — RAKIP LIDER TAHKIMI, 21 Agustos 2026.
        #
        # rakip_grace_s: buyuk-id bir rakip liderin, kalp atislarimiza
        #   RAGMEN liderlik iddiasini surdurme suresi. Bunu asarsa "kalp
        #   atisim ona ULASMIYOR" sonucuna variriz.
        #   3.0 sn secildi: normal isleyiste buyuk-id taraf TEK bir kalp
        #   atisi duyar duymaz (~100 ms) bize uyar; 3 sn ~30 kalp atisinin
        #   ardi ardina ulasmamasi demek. Bootstrap yarisi da <1 sn'de
        #   kapaniyor (21 Agustos ucusunda 80 ms olculdu).
        self.declare_parameter('rakip_grace_s', 3.0)
        # Boyun egdikten sonra kucuk-id onalmasini bastirma suresi.
        # 10.0 sn: asimetrik link birkac saniyede duzelmez; bu sure
        # dolunca durum yeniden degerlendirilir.
        self.declare_parameter('onalma_bastir_s', 10.0)
        # LIDER KILIDI — 3 Eylul 2026 operator karari. True iken lider BIR
        # KEZ secilir ve degismez. Gerekce/bedel: election.decide_change.
        self.declare_parameter('lider_kilitli', False)
        self.declare_parameter('lider_kilit_tam_kadro_s', 8.0)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._agent_count = int(self.get_parameter('agent_count').value)
        self._tick_hz = float(self.get_parameter('tick_hz').value)
        self._hb_timeout_s = (
            float(self.get_parameter('heartbeat_timeout_ms').value) / 1000.0
        )
        self._stale_s = float(
            self.get_parameter('agent_stale_timeout_s').value
        )
        self._battery_min_v = float(
            self.get_parameter('battery_min_v').value
        )
        self._rakip_grace_s = float(
            self.get_parameter('rakip_grace_s').value
        )
        self._onalma_bastir_s = float(
            self.get_parameter('onalma_bastir_s').value
        )
        # Rakip lider izleme (P1.14): kim, ne zamandan beri, son ne zaman.
        self._rakip_id = 0
        self._rakip_since = 0.0
        self._rakip_son_hb = 0.0
        self._grace_s = float(
            self.get_parameter('bootstrap_grace_s').value
        )

    def _setup_io(self) -> None:
        """Iletisim kanallarini ve servis baglantilarini kurar."""
        self._hb_pub = self.create_publisher(
            LeaderHeartbeat, '/swarm/internal/leader/heartbeat',
            _HEARTBEAT_QOS,
        )
        self._election_pub = self.create_publisher(
            ElectionResult, '/swarm/internal/election/result',
            _ELECTION_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

        for aid in range(1, self._agent_count + 1):
            self.create_subscription(
                AgentStatus, f'/swarm/public/drone{aid}/status',
                self._make_status_cb(aid), _STATUS_QOS,
            )
        self.create_subscription(
            AgentStatus, f'/swarm/internal/drone{self._agent_id}/status',
            self._make_status_cb(self._agent_id), 10,
        )

        self.create_subscription(
            LeaderHeartbeat, '/swarm/public/leader/heartbeat',
            self._on_heartbeat, _HEARTBEAT_QOS,
        )
        self.create_subscription(
            ElectionResult, '/swarm/public/election/result',
            self._on_election, _ELECTION_QOS,
        )

        self._role_client = self.create_client(
            AssignRole, f'/swarm/agent/drone{self._agent_id}/assign_role',
        )

    def _tick(self) -> None:
        """Periyodik degerlendirme yapar."""
        now = time.monotonic()
        ctx = self._ctx
        elig = election.eligible_ids(ctx, now)
        # P0.14(a): eskiden `own_airborne` geciliyordu ve yol tamamen oluydu —
        # gecis doneminde FSM ucus boyunca ARMED'da kaliyor, ARMED ise
        # AIRBORNE_STATES'te yok. Dogru sart ADAY olmak.
        own_aday = self._agent_id in elig
        effective = election.effective_set(ctx, now, own_aday, elig)

        if ctx.leader_id == 0 and effective and ctx.bootstrap_since == 0.0:
            ctx.bootstrap_since = now

        # RAKIP LIDER TAHKIMI — P1.14. decide_change'ten ONCE, cunku
        # sonucu (boyun egme) liderlik durumunu degistiriyor.
        self._rakip_tahkim(now)

        change = election.decide_change(ctx, effective, now)
        if change is not None:
            self._set_leader(*change)
        elif ctx.is_leader and self._agent_id not in elig:
            # LIDERLIGI BIRAK — P0.12(a), 20 Agustos 2026.
            #
            # decide_change devralacak biri VARSA liderligi zaten devrediyor
            # (election.py:112 `ctx.leader_id not in effective` ->
            # REASON_LEADER_FAULT). Bozuk olan tek durum kimsenin uygun
            # OLMAMASI: election.py:98-99
            #     candidate = min(effective) if effective else 0
            #     if candidate == 0: return None
            # ile fonksiyon hemen cikiyor, _set_leader HIC cagrilmiyor ve
            # ctx.is_leader True TAKILI KALIYOR.
            #
            # SAHADA OLCULDU (20 Agustos, ylp00, pervanesiz): 12 saniyelik
            # sahte ARMED enjeksiyonundan 2.8 DAKIKA sonra ucak hala
            # state=1 (IDLE), armed=false iken mesh'e 10.0 Hz
            # LeaderHeartbeat(leader_id=1) basiyordu.
            #
            # Ikinci ucusta konteyner yeniden baslatilmazsa: diger ucak arm
            # olur, kendini secer, sonra yerdeki hayalet kalp atisi gelir
            # (leader_id 1 < 3), _adopt_leader liderligi olu ucaga GERI
            # verir, bir sonraki tick geri alir -> saniyede 5-10 lider
            # degisimi, pervaneler donerken ve guided komutlarla AYNI
            # ESP-NOW kanalinda.
            #
            # NEDEN BURADA (decide_change'DEN SONRA): devir yolu oncelikli
            # kalsin. Bu dal yalniz "devralacak kimse yok AMA biz de uygun
            # degiliz" durumunu yakalar, havada calisan lider degisimi
            # mantigina dokunmaz.
            #
            # HISTEREZIS — tek tikte birakma YOK. Ayni yer testinde olculdu:
            # uygunluk TITRERSE (enjeksiyon duzeneginde sahte 20 Hz ARMED ile
            # gercek 10 Hz IDLE ayni topikte kavga ediyor) tek tiklik kapi
            # sec-birak-sec-birak dongusu uretiyor ve her cevrimde
            # EVENT_LEADER_CHANGED yayiliyor. Gercek ucusta bu titreme
            # beklenmiyor, ama `healthy` bir an dususe gecerse ayni sey
            # HAVADA olurdu.
            #
            # `grace_s` BILEREK yeniden kullanildi (yeni parametre yok):
            # secilmek icin 1.5 sn uygunluk gerekiyor, birakmak icin de
            # 1.5 sn UYGUNSUZLUK. Simetrik ve zaten sahada ayarlanmis sayi.
            if self._uygunsuz_since == 0.0:
                self._uygunsuz_since = now
            elif (now - self._uygunsuz_since) >= ctx.grace_s:
                self._liderligi_birak()
        else:
            # Uygunuz ya da lider degiliz -> histerezis sayacini sifirla.
            self._uygunsuz_since = 0.0

        # KALP ATISI: lider oldugu surece her tick yayinlanir.
        # 19 Agustos 2026'ya kadar 'own_airborne' sarti vardi (yalniz havada).
        # Kaldirildi, cunku:
        #  1) P0.11 yer testinde lider secildi ama kalp atisi hic
        #     gorulemedi — dogrulama kor kaldi (olculdu). Lider yalniz
        #     ARMED+ durumlarda var olabildigi icin (ELIGIBLE_STATES)
        #     yerdeki yayin penceresi zaten kisa: arm-kalkis arasi +
        #     yer testleri. Mesh maliyeti ucustakiyle ayni (tick_hz).
        #  2) task_reallocator'in hb zaman asimi 0.5 sn; yerde yayin
        #     olmamasi, o dugum acildiginda sahte "lider kayip" uretirdi.
        #  3) 20 Agustos 2026: uygunluk kapisi eklendi. Yukaridaki
        #     _liderligi_birak() bayragi zaten indiriyor, ama bu ikinci
        #     kapi baska bir yol (_adopt_leader / _on_election) bayragi
        #     uygun DEGILKEN kaldirirsa mesh'e hayalet kalp atisi
        #     cikmasini engelliyor. Ucuz ve geri alinabilir.
        if ctx.is_leader and self._agent_id in elig:
            self._publish_heartbeat(len(elig))

    def _rakip_tahkim(self, now: float) -> None:
        """Rakip lider iddiasini degerlendirir — P1.14, 21 Agustos 2026.

        KURAL: benden BUYUK id'li bir rakip, kalp atislarima RAGMEN
        liderlik iddiasini `rakip_grace_s` boyunca surduruyorsa, KALP
        ATISIM ONA ULASMIYOR demektir.

        NEDEN BOYUN EGIYORUZ (kucuk-id kurali bozuluyor gibi gorunse de):
        o bizi duymuyor ama biz onu DUYUYORUZ, yani calisan yon O->BIZ.
        Bir liderin isi komut YOLLAMAK; yollamasi ise yarayan taraf O.
        Kucuk-id'de israr etmek iki lideri KALICI kilar ve hicbir taraf
        digerine ulasamaz. Boyun egmek bolunmeyi TEK lidere indirir ve
        secilen lider, komutu fiilen ulastirabilen taraf olur.

        YANLIS TETIKLENME PAYI: normal isleyiste buyuk-id taraf TEK bir
        kalp atisi duyar duymaz bize uyuyor (_on_heartbeat kucuk-id dali,
        ~100 ms). Bootstrap yarisi da hizli kapaniyor — 21 Agustos
        ucusunda 80 ms olculdu. 3 sn ~30 kalp atisinin ard arda
        ulasmamasi demek; olculen en buyuk gercek boslugun (218 ms)
        13 katı.

        Rakip susarsa (hb_timeout kadar iddia gelmezse) izleme
        kendiliginden sifirlanir ve boyun egilmez.
        """
        ctx = self._ctx
        if not self._rakip_id:
            return
        if not ctx.is_leader:
            # Artik lider degiliz; rakiplik sorusu ortadan kalkti.
            self._rakip_sifirla()
            return
        if (now - self._rakip_son_hb) > ctx.hb_timeout_s:
            # Rakip iddiasini birakti (ya da duyulmaz oldu) — normale don.
            self.get_logger().info(
                f'[CONSENSUS] rakip drone{self._rakip_id} iddiasini birakti '
                f'({now - self._rakip_since:.2f} sn surdu), liderlik bende.'
            )
            self._rakip_sifirla()
            return
        if (now - self._rakip_since) < self._rakip_grace_s:
            return

        rakip = self._rakip_id
        ctx.onalma_bastir_until = now + self._onalma_bastir_s
        self.get_logger().warning(
            f'[CONSENSUS] TAHKIM: drone{rakip} {self._rakip_grace_s:.1f} sn '
            f'boyunca liderlik iddiasini surdurdu -> kalp atisim ona '
            f'ULASMIYOR (tek yonlu kopma). Liderligi ona birakiyorum; '
            f'onalma {self._onalma_bastir_s:.0f} sn bastirildi. '
            f'Bkz. YAPILACAKLAR P1.14.'
        )
        # WARNING seviyesi BILEREK: _adopt_leader'in normal INFO olayindan
        # ayrilsin ki kayitta "bu sira disi bir devir" diye gorunsun.
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_LEADER_CHANGED
        m.severity = SystemEvent.SEVERITY_WARNING
        m.source_agent_id = self._agent_id
        m.source_module = 'consensus'
        m.value = float(rakip)
        m.message = (
            f'TEK YONLU KOPMA: drone{self._agent_id} liderligi drone{rakip} '
            f'lehine birakti — kalp atisi ona ulasmiyor'
        )
        self._event_pub.publish(m)
        self._rakip_sifirla()
        self._adopt_leader(rakip, ctx.election_round, now)

    def _rakip_sifirla(self) -> None:
        """Rakip izlemesini temizler."""
        self._rakip_id = 0
        self._rakip_since = 0.0
        self._rakip_son_hb = 0.0

    def _liderligi_birak(self) -> None:
        """Kendi uygunlugunu yitiren lider liderligi birakir (P0.12a).

        `_set_leader` ile ayni islerin bir kismini yapar ama BILEREK farkli:
        - `election_round` ARTIRILMAZ. Bu bir SECIM degil, bir cekilme;
          turu artirmak komsularin mesru seciminin `msg.election_round <
          ctx.election_round` filtresine takilmasina yol acardi.
        - `ElectionResult` YAYINLANMAZ. Yeni lider yok, duyurulacak sonuc
          da yok. `_pub_leader_changed(0)` ile yalnizca "lider kalmadi"
          bilgisi veriliyor.

        Sonraki arm'da normal yol isler: effective dolar, bootstrap saati
        kurulur, grace sonrasi secim yapilir.
        """
        ctx = self._ctx
        eski = ctx.leader_id
        ctx.is_leader = False
        ctx.leader_id = 0
        ctx.last_hb_time = 0.0
        ctx.bootstrap_since = 0.0
        self._uygunsuz_since = 0.0

        self.get_logger().info(
            f'[CONSENSUS] liderlik BIRAKILDI (eski lider {eski}, ben='
            f'{self._agent_id}): kendi uygunlugumu yitirdim ve devralacak '
            f'uygun ajan yok. Kalp atisi kesildi.'
        )
        self._pub_leader_changed(0)
        self._apply_role()

    def _set_leader(self, new_id: int, reason: int) -> None:
        """Yeni lider durumunu uygular."""
        ctx = self._ctx
        old = ctx.leader_id
        ctx.election_round = (ctx.election_round + 1) % 256
        ctx.leader_id = new_id
        ctx.is_leader = (new_id == self._agent_id)
        ctx.last_hb_time = time.monotonic()
        ctx.bootstrap_since = 0.0

        self.get_logger().info(
            f'[CONSENSUS] Lider: {old} -> {new_id} '
            f'(round={ctx.election_round}, ben={self._agent_id})'
        )

        if ctx.is_leader:
            self._publish_election_result(new_id, reason)
        self._pub_leader_changed(new_id)
        self._apply_role()

    def _apply_role(self) -> None:
        """Kendi rolunu yerel servisle uygular."""
        ctx = self._ctx
        own = ctx.own()
        if own is None or own.state not in ELIGIBLE_STATES:
            return

        desired = (
            AssignRole.Request.ROLE_LEADER if ctx.is_leader
            else AssignRole.Request.ROLE_FOLLOWER
        )
        if desired == ctx.applied_role:
            return
        if not self._role_client.service_is_ready():
            return

        req = AssignRole.Request()
        req.target_agent_id = self._agent_id
        req.role = desired
        req.reason = 'consensus_election'
        self._role_client.call_async(req)
        ctx.applied_role = desired

    def _make_status_cb(self, agent_id: int):
        """Belirli bir ajan icin status callback kapatmasi doner."""
        def _cb(msg: AgentStatus) -> None:
            self._ctx.update_status(agent_id, msg, time.monotonic())
        return _cb

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Lider hb verisini isler."""
        ctx = self._ctx
        if msg.leader_id == self._agent_id:
            return
        now = time.monotonic()
        if msg.leader_id == ctx.leader_id:
            ctx.last_hb_time = now
        elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id:
            self._adopt_leader(msg.leader_id, msg.election_round, now)
        elif ctx.is_leader:
            # RAKIP LIDER — P1.14, 21 Agustos 2026.
            #
            # Buraya yalniz "ben liderim ve BENDEN BUYUK id'li baska biri de
            # lider olduğunu soyluyor" halinde duseriz. Eskiden bu dal HIC
            # YOKTU: kucuk-id taraf rakibi tamamen yok sayiyor, log bile
            # basmiyordu. Sonucu iki katliydi:
            #   1. Split-brain kucuk-id tarafta GORUNMEZ (ucus kaydinda iz yok)
            #   2. Cozum tek yonluydu — yalniz buyuk-id taraf bize uyarak
            #      cikabiliyordu, o da BIZIM kalp atisimizi duymasina bagli.
            #      Yani kurtulus yolu, kopmus olan yonun ta kendisi.
            #
            # Asimetrik linkte (biz->o kopuk, o->biz calisiyor) bu KALICI ve
            # SESSIZ iki lider demek. 21 Agustos ucusunda olculdu ki lider
            # kimligi mesh'e kalp atisiyla tasiniyor (secim cercevesi hic
            # gelmedi), yani yakinsamanin fiili tek yolu bu.
            #
            # Burada yalniz IZLIYORUZ; karar _tik'te veriliyor (rakip susarsa
            # kendiliginden sifirlanabilsin diye).
            if msg.leader_id != self._rakip_id:
                self._rakip_id = int(msg.leader_id)
                self._rakip_since = now
                self.get_logger().warning(
                    f'[CONSENSUS] RAKIP LIDER: drone{msg.leader_id} de lider '
                    f'oldugunu soyluyor (ben={self._agent_id}, kucuk id benim). '
                    f'Kalp atisim ona ulasiyorsa {self._rakip_grace_s:.1f} sn '
                    f'icinde vazgecmeli.'
                )
            self._rakip_son_hb = now

    def _adopt_leader(
        self, leader_id: int, election_round: int, now: float,
    ) -> None:
        """Liderlik durumunu gunceller."""
        ctx = self._ctx
        was_leader = ctx.is_leader
        ctx.leader_id = leader_id
        ctx.is_leader = (leader_id == self._agent_id)
        ctx.election_round = max(ctx.election_round, election_round)
        ctx.last_hb_time = now
        if was_leader and not ctx.is_leader:
            self.get_logger().info(
                f'[CONSENSUS] Split-brain cozuldu: liderligi '
                f'drone{leader_id} lehine biraktim.'
            )
        self._apply_role()

    def _on_election(self, msg: ElectionResult) -> None:
        """Lider secim sonucunu alir.

        Eskimis mesaj filtresi KAYNAK BASINA ve incarnation duyarli. Gerekcesi
        ElectionResult.msg'de ayrintili yazili; kisaca: sequence_num yayinci
        yeniden baslayinca 0'a doner ve tek global sayac tutulursa yeniden
        baslayan (ya da yeni secilen) liderin butun sonuclari SESSIZCE duser.
        """
        ctx = self._ctx
        kaynak = int(msg.triggered_by_agent_id)
        inc = int(msg.incarnation)
        kabul, inc_degisti = election.seq_kabul(
            ctx.seen_seq, kaynak, inc, int(msg.sequence_num)
        )
        if inc_degisti:
            # Sessiz kalmamali: sahada "secim neden uygulanmadi" sorusunun
            # cevabi tam burada.
            self.get_logger().info(
                f'[CONSENSUS] ajan {kaynak} yeniden baslamis '
                f'(incarnation -> {inc}), seq sayaci sifirlandi'
            )
        if not kabul:
            return
        ctx.seen_seq[kaynak] = (inc, int(msg.sequence_num))
        if msg.election_round < ctx.election_round:
            return

        ctx.election_round = max(ctx.election_round, msg.election_round)
        ctx.leader_id = msg.new_leader_id
        ctx.is_leader = (msg.new_leader_id == self._agent_id)
        ctx.last_hb_time = time.monotonic()
        self._apply_role()

    def _publish_heartbeat(self, active_count: int) -> None:
        """Heartbeat yayinlar."""
        ctx = self._ctx
        m = LeaderHeartbeat()
        m.stamp = self.get_clock().now().to_msg()
        m.leader_id = self._agent_id
        ctx.hb_seq = (ctx.hb_seq + 1) % _U32
        m.sequence_num = ctx.hb_seq
        m.election_round = ctx.election_round
        m.active_agent_count = active_count
        m.mission_active = ctx.mission_active
        self._hb_pub.publish(m)

    def _publish_election_result(self, leader_id: int, reason: int) -> None:
        """Secim sonucunu yayinlar."""
        ctx = self._ctx
        m = ElectionResult()
        m.stamp = self.get_clock().now().to_msg()
        ctx.out_seq = (ctx.out_seq + 1) % _U32
        m.sequence_num = ctx.out_seq
        m.incarnation = self._incarnation
        m.new_leader_id = leader_id
        m.election_round = ctx.election_round
        m.triggered_by_agent_id = self._agent_id
        m.reason = reason
        m.confirmed_by_agent_ids = []
        m.message = f'Lider: drone{leader_id} (round {ctx.election_round})'
        self._election_pub.publish(m)

    def _pub_leader_changed(self, leader_id: int) -> None:
        """Lider degisimi sistem olayini tetikler."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_LEADER_CHANGED
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.source_module = 'consensus'
        m.value = float(leader_id)
        # leader_id = 0 -> lider YOK. `_liderligi_birak` bunu kullaniyor;
        # 'Yeni lider: drone0' yaniltici olurdu (drone0 diye bir ucak yok).
        m.message = (
            f'Yeni lider: drone{leader_id}' if leader_id
            else 'Lider kalmadi (uygun ajan yok)'
        )
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ConsensusNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
