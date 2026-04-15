# Temel İmaj: Ubuntu 24.04 (Noble) + ROS 2 Jazzy
ARG BASE_IMAGE=osrf/ros
ARG BASE_TAG=jazzy-desktop-full
FROM ${BASE_IMAGE}:${BASE_TAG}

# Kurulum sırasında soru sorulmasını engelle
ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic

# Gerekli Paketlerin Kurulumu
# DÜZELTME YAPILDI: 'libgl1-mesa-glx' yerine 'libgl1' kullanıldı.
RUN apt-get update && apt-get install -y \
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
    && rm -rf /var/lib/apt/lists/*

# ====================================================================
# YELPENÇE PX4 SITL PYTHON BAĞIMLILIKLARI 
# ====================================================================
RUN pip3 install --break-system-packages kconfiglib jinja2 jsonschema pyros-genmsg empy packaging toml \
    flask flask-socketio eventlet opencv-python "numpy<2.0.0" pyzbar
# ====================================================================

# ====================================================================
# MICRO XRCE-DDS AGENT KURULUMU (ROS 2 - PX4 Haberleşme Köprüsü)
# ====================================================================
RUN git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/Micro-XRCE-DDS-Agent \
    && cd /tmp/Micro-XRCE-DDS-Agent \
    && mkdir build && cd build \
    && cmake .. \
    && make \
    && make install \
    && ldconfig /usr/local/lib/ \
    && rm -rf /tmp/Micro-XRCE-DDS-Agent
# ====================================================================

# ROS 2 İletişim Altyapısını FastDDS Olarak Ayarla
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp 
# QR kod üretimi için Python bağımlılığı
RUN pip3 install --break-system-packages qrcode[pil]

# ====================================================================
# QGROUNDCONTROL BAĞIMLILIKLARI (QGC dosyası host'tan volume ile gelir)
# ====================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    fuse libfuse2 libpulse-mainloop-glib0 \
    && rm -rf /var/lib/apt/lists/*
# ====================================================================

# --- YELPENÇE ÖZELLEŞTİRMESİ ---
ARG USERNAME=yelpence
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# KRİTİK ADIM: UID Çakışma Çözücü
# Eğer 1000 ID'li bir kullanıcı (ubuntu) zaten varsa onu siler.
RUN if id -u $USER_UID >/dev/null 2>&1; then userdel -r $(id -un $USER_UID); fi

# Takım Kullanıcısını (yelpence) oluştur
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Kullanıcı Ortamına Geçiş
USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR /home/$USERNAME/ros2_ws

# .bashrc Ayarları
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
RUN echo "if [ -f /home/$USERNAME/ros2_ws/install/setup.bash ]; then source /home/$USERNAME/ros2_ws/install/setup.bash; fi" >> ~/.bashrc

# Nvidia Uyumluluk Değişkenleri
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# Entrypoint Scriptini Kopyala
COPY --chown=$USERNAME:$USERNAME docker/entrypoint.sh /entrypoint.sh
RUN sudo chmod +x /entrypoint.sh

# Başlangıç Noktası
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
