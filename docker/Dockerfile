# 1. Aşama: Temel İmaj ve Bağımlılıklar
ARG BASE_IMAGE=osrf/ros
ARG BASE_TAG=jazzy-desktop-full
FROM ${BASE_IMAGE}:${BASE_TAG}

# Kurulum sırasında etkileşimi kapat
ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic

# Sistem Paketlerinin Kurulumu (Tek katmanda ve temizlik yaparak)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-ros-gz \
    ros-jazzy-gz-ros2-control \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    ros-jazzy-xacro \
    ros-jazzy-rqt* \
    ros-jazzy-rmw-cyclonedds-cpp \
    python3-pip \
    python3-rosdep \
    iputils-ping \
    net-tools \
    nano \
    git \
    wget \
    curl \
    libgl1 \
    libgl1-mesa-dri \
    libzbar0 \
    fuse \
    libfuse2 \
    libpulse-mainloop-glib0 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Python Bağımlılıkları
RUN pip3 install --break-system-packages \
    kconfiglib jinja2 jsonschema pyros-genmsg empy packaging toml \
    flask flask-socketio eventlet opencv-python "numpy<2.0.0" pyzbar qrcode[pil]

# Micro XRCE-DDS Agent Kurulumu
RUN git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/Micro-XRCE-DDS-Agent \
    && cd /tmp/Micro-XRCE-DDS-Agent && mkdir build && cd build \
    && cmake .. && make && make install \
    && ldconfig /usr/local/lib/ \
    && rm -rf /tmp/Micro-XRCE-DDS-Agent

# 2. Aşama: Kullanıcı ve Yetki Yapılandırması
ARG USERNAME=yelpence
# KRİTİK: Bu değerleri build sırasında host makinenizden alacağız
ARG USER_UID=1000
ARG USER_GID=1000

# Eğer 1000 ID'li varsayılan bir 'ubuntu' kullanıcısı varsa sil (Çakışmayı önler)
RUN if id -u $USER_UID >/dev/null 2>&1; then userdel -r $(id -un $USER_UID); fi || true

# Grubu ve Kullanıcıyı oluştur
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Çevresel Değişkenler
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# Entrypoint Hazırlığı (ROOT olarak)
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Kullanıcıya geçiş
USER $USERNAME
WORKDIR /home/$USERNAME/ros2_ws

# .bashrc Ayarları
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc \
    && echo 'if [ -f /home/$USERNAME/ros2_ws/install/setup.bash ]; then source /home/$USERNAME/ros2_ws/install/setup.bash; fi' >> ~/.bashrc

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]

