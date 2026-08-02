import os, rclpy, time
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy
from mavros_msgs.srv import MessageInterval
from mavros_msgs.msg import ExtendedState
# AGENT_ID env ile parametrik (verilmezse 1). ns=/drone_${AGENT_ID}.
AGENT_ID = os.environ.get("AGENT_ID", "1")
rclpy.init(); n = Node("hiz2")
c = n.create_client(MessageInterval, f"/drone_{AGENT_ID}/mavros/set_message_interval")
if c.wait_for_service(timeout_sec=15.0):
    # GPS'i kis, bataryaya yer ac
    for mid, ad, hz in [(24,"GPS_RAW",5.0), (1,"SYS_STATUS",5.0), (147,"BATTERY",5.0),
                        (31,"ATTITUDE_QUAT",20.0), (331,"ODOMETRY",20.0), (33,"GLOBAL_POS",10.0)]:
        r = MessageInterval.Request(); r.message_id = mid; r.message_rate = hz
        f = c.call_async(r); rclpy.spin_until_future_complete(n, f, timeout_sec=6.0)
        res = f.result()
        print("  %-14s -> %5.1f Hz : %s" % (ad, hz, "OK" if (res and res.success) else "RED"))
else:
    print("  servis yok")
rclpy.shutdown()
