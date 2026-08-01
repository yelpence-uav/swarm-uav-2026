import rclpy
from rclpy.node import Node
from swarm_interfaces.srv import TriggerMission

rclpy.init()
n = Node('start_trigger_once')
cli = n.create_client(TriggerMission, '/swarm/mission/trigger')
print('servis bekleniyor (60 sn)...', flush=True)
if not cli.wait_for_service(timeout_sec=60.0):
    print('HATA: trigger servisi 60 sn icinde bulunamadi', flush=True)
    raise SystemExit(1)
print('servis bulundu, START gonderiliyor', flush=True)
req = TriggerMission.Request()
req.mission_id = 1
req.command = 1
req.team_id = '752825'
fut = cli.call_async(req)
rclpy.spin_until_future_complete(n, fut, timeout_sec=15.0)
print('YANIT:', fut.result(), flush=True)
n.destroy_node(); rclpy.shutdown()
