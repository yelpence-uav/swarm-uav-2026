# Uçtan uca hazır bir simülasyon konteyneri için hazırlanmış Dockerfile.

# Temel İmaj---------------------------
ARG BASE_IMAGE=osrf/ros
ARG BASE_TAG=jazzy-desktop-full
FROM ${BASE_IMAGE}:${BASE_TAG}
ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic
# --------------------------------------

# Sistem Paketleri --------------------
RUN apt-get update && apt-get install -y \
    # ros-jazzy paketleri. https://index.ros.org/ adresinde paketler bulunabilir.
    ros-jazzy-ros-gz \
    ros-jazzy-gz-ros2-control \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    ros-jazzy-xacro \
    ros-jazzy-rqt* \
    ros-jazzy-rmw-cyclonedds-cpp \
    # Ubuntu sistem paketleri. https://packages.ubuntu.com/ adresinde paketler bulunabilir.
    python3-pip \
    python3-rosdep \
    python3-venv \
    python3-dev \
    iputils-ping \
    net-tools \
    nano \
    git \
    wget \
    curl \
    libgl1 \
    libgl1-mesa-dri \
    openssh-server \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
# --------------------------------------

# Kullanıcı Ayarları ------------------- 
ARG USERNAME=yelpence
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Kullanıcı ve grup çakışmalarını temizle 
RUN if id -u $USER_UID >/dev/null 2>&1; then userdel -r $(id -un $USER_UID) || true; fi \
    && if getent group $USER_GID >/dev/null 2>&1; then groupdel $(getent group $USER_GID | cut -d: -f1) || true; fi

# Takım Kullanıcısını oluştur ve sudo yetkisi ver
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME
# --------------------------------------

# SSH Yapılandırması-------------------- 
RUN echo 'root:yelpence2026' | chpasswd \
    && echo 'yelpence:yelpence2026' | chpasswd

# SSH dizinini oluştur
RUN mkdir /var/run/sshd

# Root girişine ve şifreli girişe izin ver
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

EXPOSE 22
# --------------------------------------

# Micro Xrce-DDS Agent Uyumluluk--------
RUN git clone --depth 1 --branch v3.0.1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git /tmp/Micro-XRCE-DDS-Agent \
    && cd /tmp/Micro-XRCE-DDS-Agent \
    && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release \
    -DUAGENT_FASTMETRICS=OFF \
    -DUAGENT_BUILD_EXECUTABLE=ON .. \
    && make -j$(nproc) \
    && make install \
    && ldconfig /usr/local/lib/ \
    && cd / \
    && rm -rf /tmp/Micro-XRCE-DDS-Agent \
    && apt-get purge -y --auto-remove \
    && rm -rf /var/lib/apt/lists/*
# --------------------------------------

# Başlangıç Betiği----------------------
COPY --chown=$USERNAME:$USERNAME docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
# --------------------------------------

# ROS2 CycloneDDS Ayarı-----------------
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ENV ROS_DOMAIN_ID=0
# --------------------------------------

# Nvidia Uyumluluk----------------------
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all
# --------------------------------------

# Kullanıcı Ortamına Betiği-------------
# Bu noktadan sonra root yetkisi bulunmaz. Root yetkisi gereken işlemler buranın üstüne alınmalıdır.
RUN mkdir -p /home/$USERNAME/ros2_ws && chown -R $USERNAME:$USERNAME /home/$USERNAME/ros2_ws
USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR /home/$USERNAME/ros2_ws
# --------------------------------------

# Python Bağımlılıkları----------------- 
# src/requirements.txt kullanılarak yönetilir. Eklemek istediğiniz bağımlılığı buraya değil dosyaya ekleyin.
RUN python3 -m venv /home/$USERNAME/venv
ENV PATH="/home/$USERNAME/venv/bin:$PATH"

COPY --chown=$USERNAME:$USERNAME src/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt
# --------------------------------------

# PX4 Autopilot Yapılandırması----------
# src klasörünü oluşturur, repoları çeker, colcon ignore ekler ve x500 ayarlarını yapar.
RUN mkdir -p src \
    && git clone --depth 1 --branch v1.15.0 --recursive https://github.com/PX4/PX4-Autopilot.git src/PX4-Autopilot \
    && find src/PX4-Autopilot -name ".git" -type d -exec rm -rf {} + \
    && find src/PX4-Autopilot -name ".github" -type d -exec rm -rf {} + \
    && touch src/PX4-Autopilot/COLCON_IGNORE \
    && git clone --depth 1 https://github.com/PX4/px4_msgs.git src/px4_msgs \
    && find src/px4_msgs -name ".git" -type d -exec rm -rf {} + \
    && { \
    echo ""; \
    echo "# YELPENCE SURU IHA - Otonom Ucus Izinleri (SIMULASYON)"; \
    echo "param set-default NAV_DLL_ACT 0"; \
    echo "param set-default NAV_RCL_ACT 0"; \
    echo "param set-default COM_RCL_EXCEPT 4"; \
    } >> src/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/4001_gz_x500
# --------------------------------------

# .bashrc Ayarları----------------------
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc \
    && echo "if [ -f ~/ros2_ws/install/setup.bash ]; then source ~/ros2_ws/install/setup.bash; fi" >> ~/.bashrc \
    && echo "source ~/venv/bin/activate" >> ~/.bashrc \
    && echo "# --- Yelpençe Kısayolları ---" >> ~/.bashrc \
    && echo "alias ajan='MicroXRCEAgent udp4 -p 8888'" >> ~/.bashrc \
    && echo "alias build_swarm='cd ~/ros2_ws && colcon build --symlink-install --packages-select px4_msgs swarm && source install/setup.bash'" >> ~/.bashrc \
    && echo "alias ws='cd ~/ros2_ws'" >> ~/.bashrc
# --------------------------------------

# Konteyner Başlatma--------------------
USER $USERNAME
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]
# --------------------------------------
