"""Görev/rol yeniden dağıtım modülü (task reallocator).

Sürüden ayrılan veya yedek durumdan katılan İHA'ların rollerini ve
formasyon koordinatlarını (slot/rank) otonom olarak yeniden dağıtır.

Saf matematik çekirdeği (``task_reallocator_core``) ROS'tan bağımsızdır;
node katmanı (``task_reallocator_node``) bu çekirdeği mesajlara bağlar.
"""
