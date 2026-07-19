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
    # MAVROS: uXRCE-DDS yerine MAVLink <-> ROS2 kopru katmani.
    # mavros: cekirdek eklentiler | extras: ek eklentiler (gps_rtk vb.)
    # mavros-msgs: State/CommandBool/SetMode gibi mesaj-servis tanimlari.
    ros-jazzy-mavros \
    ros-jazzy-mavros-extras \
    ros-jazzy-mavros-msgs \
    # Ubuntu sistem paketleri. https://packages.ubuntu.com/ adresinde paketler bulunabilir.
    python3-pip \
    python3-rosdep \
    python3-venv \
    python3-dev \
    iputils-ping \
    python3-kconfiglib \
    python3-jinja2 \
    python3-jsonschema \
    libgtest-dev \
    net-tools \
    nano \
    git \
    wget \
    curl \
    libgl1 \
    libgl1-mesa-dri \
    openssh-server \
    cmake \
    tmux \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
# --------------------------------------

# MAVROS GeographicLib Veri Setleri ----
# MAVROS, GPS (elipsoid) yuksekligini deniz seviyesi (geoid) yuksekligine
# cevirmek icin geoid/gravity/magnetic veri setlerine ihtiyac duyar. Bu
# setler kurulmazsa mavros_node acilista GeographicLib istisnasi ile olur.
# Script mavros ile birlikte gelir; internetten veri setlerini indirir.
RUN /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh
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

# .bashrc Ayarları----------------------
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc \
    && echo "if [ -f ~/ros2_ws/install/setup.bash ]; then source ~/ros2_ws/install/setup.bash; fi" >> ~/.bashrc \
    && echo "source ~/venv/bin/activate" >> ~/.bashrc 
# --------------------------------------

# Konteyner Başlatma--------------------
USER $USERNAME
CMD ["/bin/bash"]
# --------------------------------------
