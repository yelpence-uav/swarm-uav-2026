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
    && rm -rf /var/lib/apt/lists/*

# ====================================================================
# YELPENÇE PX4 SITL PYTHON BAĞIMLILIKLARI 
# ====================================================================
RUN pip3 install kconfiglib jinja2 jsonschema pyros-genmsg empy packaging toml numpy --break-system-packages
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

# 1. Temel ROS 2 ve Çalışma Alanı Kurulumu
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
RUN echo "if [ -f /home/$USERNAME/ros2_ws/install/setup.bash ]; then source /home/$USERNAME/ros2_ws/install/setup.bash; fi" >> ~/.bashrc

# 2. Ağ ve DDS İletişim Otomasyonu (Senin İstediğin Kısım)
RUN echo "export ROS_DOMAIN_ID=0" >> ~/.bashrc
RUN echo "export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST" >> ~/.bashrc
RUN echo "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp" >> ~/.bashrc

# 3. Hayat Kurtaran Kısayollar (Alias)
# Ajanı tek kelimeyle başlatmak için:
RUN echo "alias ajan='MicroXRCEAgent udp4 -p 8888'" >> ~/.bashrc
# Kodu derleyip hemen source etmek için:
RUN echo "alias build_swarm='cd ~/ros2_ws && colcon build --packages-select swarm && source install/setup.bash'" >> ~/.bashrc
# Hızlıca kök dizine gitmek için:
RUN echo "alias ws='cd ~/ros2_ws'" >> ~/.bashrc



# Nvidia Uyumluluk Değişkenleri
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# Entrypoint Scriptini Kopyala
COPY --chown=$USERNAME:$USERNAME docker/entrypoint.sh /entrypoint.sh
RUN sudo chmod +x /entrypoint.sh

# Başlangıç Noktası
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
