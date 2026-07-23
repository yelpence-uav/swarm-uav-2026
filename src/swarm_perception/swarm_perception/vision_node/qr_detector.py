# Copyright 2026 Yelpence TEKNOFEST 2026
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
qr_detector.py.

Pyzbar kullanarak BGR görüntülerde QR kod tespiti yapan saf modül.
ROS 2 bağımlılığı taşımaz, yalnızca numpy ve pyzbar kullanır.

QR içeriği yarışma şartnamesindeki JSON şemasıdır:

    {"qr": 1, "w": 4,
     "mis": [ [["frm","ok",6], ["mnv",-10,0], ["alt",20]],
              [["frm","v",8],  ["mnv",0,10],  ["alt",25]] ],
     "team": {"1":[1,3], "2":[2,2], ...}}

qr    : mevcut QR numarası
w     : her görev arası bekleme (saniye)
mis   : görev paketleri (1-tabanlı numaralanır)
team  : "takım_slotu": [paket_numarası, sonraki_qr]

Her takım kendi slotuna bakıp yalnız ilgili paketi uygular. Paket, sırayla
formasyon/manevra/irtifa ya da tek başına ayrılma komutları içerir; bunlar
tek bir QRMissionData'ya düzleştirilir (mission_fsm alt-adımlara böler).
"""

import json
from typing import Any, Dict, List

import numpy as np

from pyzbar.pyzbar import decode

# QR komut kısaltmaları -> QRMissionData enum değerleri.
_FORMATION_CODES = {'ok': 1, 'v': 2, 'l': 3}     # OKBASI / V / CIZGI
_COLOR_CODES = {'r': 1, 'b': 2}                   # RED / BLUE


class QRDetector:
    """Goruntudeki QR kodlarini bulup ayristiran sinif."""

    def __init__(
        self, min_confidence: float = 0.5, team_slot: int = 1
    ) -> None:
        """
        Aciklama: QRDetector sinifini ilklendirir.

        Args:
            min_confidence (float): Asgari güven eşiği (pyzbar desteklemez,
                ancak mimari uyumu için korunmuştur).
            team_slot (int): Bu takımın QR "team" tablosundaki slot numarası
                (1-5). Yarışma günü jüri tarafından bildirilir. Yanlış slot
                yanlış görev paketi ve yanlış rota demektir.
        """
        self._min_confidence = min_confidence
        self._team_slot = int(team_slot)

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        BGR goruntu uzerindeki QR kodlari bulur ve ayristirir.

        Args:
            image: cv2 formatinda BGR goruntu matrisi.

        Returns:
            List[Dict[str, Any]]: Ayristirilmis QR veri sozluk listesi.
        """
        if image is None or image.size == 0:
            return []

        decoded_objects = decode(image)
        results = []
        for obj in decoded_objects:
            try:
                raw_text = obj.data.decode('utf-8')
            except UnicodeDecodeError:
                continue

            rect = obj.rect
            img_h, img_w = image.shape[:2]

            qr_data = {
                'raw_text': raw_text,
                'image_x': float(rect.left + rect.width / 2) / img_w,
                'image_y': float(rect.top + rect.height / 2) / img_h,
                'image_width': float(rect.width) / img_w,
                'image_height': float(rect.height) / img_h,
            }

            parsed_fields = self._parse_qr_text(raw_text)
            qr_data.update(parsed_fields)
            results.append(qr_data)

        return results

    def _blank_result(self) -> Dict[str, Any]:
        """Tüm alanları nötr olan boş bir sonuç sözlüğü döndürür."""
        return {
            'team_id': '',
            'qr_id': 0,
            'qr_seq': 0,
            'next_qr': 0,
            'formation_type': 0,
            'spacing_m': 0.0,
            'altitude_agl_m': 0.0,
            'pitch_deg': 0.0,
            'roll_deg': 0.0,
            'yaw_deg': 0.0,
            'wait_s': 0.0,
            'target_agent_id': 0,
            'detach_color': 0,
            'detach_wait_s': 0.0,
            'formation_active': False,
            'target_active': False,
            'maneuver_active': False,
            'altitude_active': False,
            'detach_active': False,
            'complete_mission': False,
            'valid': False,
            'error_message': '',
        }

    def _parse_qr_text(self, text: str) -> Dict[str, Any]:
        """
        Şartname JSON'ını ayrıştırıp bu takımın görev paketini düzleştirir.

        Takım tablosundan (team[slot] = [paket_no, sonraki_qr]) kendi
        paketimizi seçer, paketteki frm/mnv/alt/leav komutlarını tek bir
        QRMissionData sözlüğüne çevirir.

        Args:
            text (str): QR kodundan okunan ham JSON metni.

        Returns:
            Dict[str, Any]: QRMissionData alanlarıyla eşleşen sözlük.
        """
        parsed = self._blank_result()

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed['error_message'] = 'QR JSON cozulemedi'
            return parsed

        try:
            parsed['qr_id'] = int(data['qr'])
            parsed['wait_s'] = float(data['w'])
            packages = data['mis']
            team_table = data['team']
        except (KeyError, TypeError, ValueError):
            parsed['error_message'] = 'QR sema alanlari eksik'
            return parsed

        slot = str(self._team_slot)
        if slot not in team_table:
            parsed['error_message'] = f'Takim slotu {slot} tabloda yok'
            return parsed

        try:
            package_no, next_qr = team_table[slot]
            package_no = int(package_no)
            parsed['next_qr'] = int(next_qr)
        except (ValueError, TypeError):
            parsed['error_message'] = 'Takim tablosu girdisi bozuk'
            return parsed

        parsed['target_active'] = True
        # sonraki_qr == 0 -> dinamik senaryo bitti, baslangica don.
        parsed['complete_mission'] = parsed['next_qr'] == 0

        # Paket numarasi 1-tabanli; mis listesi 0-tabanli.
        idx = package_no - 1
        if not isinstance(packages, list) or not (0 <= idx < len(packages)):
            parsed['error_message'] = f'Paket {package_no} listede yok'
            return parsed

        for command in packages[idx]:
            try:
                self._apply_command(parsed, command)
            except (ValueError, TypeError, IndexError) as exc:
                parsed['error_message'] = str(exc)
                return parsed

        parsed['valid'] = True
        return parsed

    def _apply_command(
        self, parsed: Dict[str, Any], command: List[Any]
    ) -> None:
        """
        Tek bir görev komutunu ([op, ...]) sonuç sözlüğüne uygular.

        frm  -> formasyon (tip, aralik_m)
        mnv  -> manevra (pitch_deg, roll_deg)
        alt  -> irtifa (metre)
        leav -> suruden ayrilma (drone_id, renk)

        Args:
            parsed (Dict[str, Any]): Verilerin saklandığı sözlük.
            command (List[Any]): [operatör, argümanlar...] biçiminde komut.
        """
        op = command[0]

        if op == 'frm':
            parsed['formation_active'] = True
            parsed['formation_type'] = _FORMATION_CODES.get(command[1], 0)
            parsed['spacing_m'] = float(command[2])
        elif op == 'mnv':
            parsed['maneuver_active'] = True
            parsed['pitch_deg'] = float(command[1])
            parsed['roll_deg'] = float(command[2])
        elif op == 'alt':
            parsed['altitude_active'] = True
            parsed['altitude_agl_m'] = float(command[1])
        elif op == 'leav':
            parsed['detach_active'] = True
            parsed['target_agent_id'] = int(command[1])
            parsed['detach_color'] = _COLOR_CODES.get(command[2], 0)
        else:
            raise ValueError(f'Bilinmeyen komut: {op}')
