


/**
 * Baudrate for the GPS 1 Serial Port
 *
 * Configure the Baudrate for the GPS 1 Serial Port.
 *
 * Note: certain drivers such as the GPS can determine the Baudrate automatically.
 *
 * @value 0 Auto
 * @value 50 50 8N1
 * @value 75 75 8N1
 * @value 110 110 8N1
 * @value 134 134 8N1
 * @value 150 150 8N1
 * @value 200 200 8N1
 * @value 300 300 8N1
 * @value 600 600 8N1
 * @value 1200 1200 8N1
 * @value 1800 1800 8N1
 * @value 2400 2400 8N1
 * @value 4800 4800 8N1
 * @value 9600 9600 8N1
 * @value 19200 19200 8N1
 * @value 38400 38400 8N1
 * @value 57600 57600 8N1
 * @value 115200 115200 8N1
 * @value 230400 230400 8N1
 * @value 460800 460800 8N1
 * @value 500000 500000 8N1
 * @value 921600 921600 8N1
 * @value 1000000 1000000 8N1
 * @value 1500000 1500000 8N1
 * @value 2000000 2000000 8N1
 * @value 3000000 3000000 8N1
 * @group Serial
 * @reboot_required true
 */
PARAM_DEFINE_INT32(SER_GPS1_BAUD, 0);

/**
 * Baudrate for the TELEM 1 Serial Port
 *
 * Configure the Baudrate for the TELEM 1 Serial Port.
 *
 * Note: certain drivers such as the GPS can determine the Baudrate automatically.
 *
 * @value 0 Auto
 * @value 50 50 8N1
 * @value 75 75 8N1
 * @value 110 110 8N1
 * @value 134 134 8N1
 * @value 150 150 8N1
 * @value 200 200 8N1
 * @value 300 300 8N1
 * @value 600 600 8N1
 * @value 1200 1200 8N1
 * @value 1800 1800 8N1
 * @value 2400 2400 8N1
 * @value 4800 4800 8N1
 * @value 9600 9600 8N1
 * @value 19200 19200 8N1
 * @value 38400 38400 8N1
 * @value 57600 57600 8N1
 * @value 115200 115200 8N1
 * @value 230400 230400 8N1
 * @value 460800 460800 8N1
 * @value 500000 500000 8N1
 * @value 921600 921600 8N1
 * @value 1000000 1000000 8N1
 * @value 1500000 1500000 8N1
 * @value 2000000 2000000 8N1
 * @value 3000000 3000000 8N1
 * @group Serial
 * @reboot_required true
 */
PARAM_DEFINE_INT32(SER_TEL1_BAUD, 57600);

/**
 * Baudrate for the TELEM 2 Serial Port
 *
 * Configure the Baudrate for the TELEM 2 Serial Port.
 *
 * Note: certain drivers such as the GPS can determine the Baudrate automatically.
 *
 * @value 0 Auto
 * @value 50 50 8N1
 * @value 75 75 8N1
 * @value 110 110 8N1
 * @value 134 134 8N1
 * @value 150 150 8N1
 * @value 200 200 8N1
 * @value 300 300 8N1
 * @value 600 600 8N1
 * @value 1200 1200 8N1
 * @value 1800 1800 8N1
 * @value 2400 2400 8N1
 * @value 4800 4800 8N1
 * @value 9600 9600 8N1
 * @value 19200 19200 8N1
 * @value 38400 38400 8N1
 * @value 57600 57600 8N1
 * @value 115200 115200 8N1
 * @value 230400 230400 8N1
 * @value 460800 460800 8N1
 * @value 500000 500000 8N1
 * @value 921600 921600 8N1
 * @value 1000000 1000000 8N1
 * @value 1500000 1500000 8N1
 * @value 2000000 2000000 8N1
 * @value 3000000 3000000 8N1
 * @group Serial
 * @reboot_required true
 */
PARAM_DEFINE_INT32(SER_TEL2_BAUD, 921600);

/**
 * Baudrate for the TELEM/SERIAL 4 Serial Port
 *
 * Configure the Baudrate for the TELEM/SERIAL 4 Serial Port.
 *
 * Note: certain drivers such as the GPS can determine the Baudrate automatically.
 *
 * @value 0 Auto
 * @value 50 50 8N1
 * @value 75 75 8N1
 * @value 110 110 8N1
 * @value 134 134 8N1
 * @value 150 150 8N1
 * @value 200 200 8N1
 * @value 300 300 8N1
 * @value 600 600 8N1
 * @value 1200 1200 8N1
 * @value 1800 1800 8N1
 * @value 2400 2400 8N1
 * @value 4800 4800 8N1
 * @value 9600 9600 8N1
 * @value 19200 19200 8N1
 * @value 38400 38400 8N1
 * @value 57600 57600 8N1
 * @value 115200 115200 8N1
 * @value 230400 230400 8N1
 * @value 460800 460800 8N1
 * @value 500000 500000 8N1
 * @value 921600 921600 8N1
 * @value 1000000 1000000 8N1
 * @value 1500000 1500000 8N1
 * @value 2000000 2000000 8N1
 * @value 3000000 3000000 8N1
 * @group Serial
 * @reboot_required true
 */
PARAM_DEFINE_INT32(SER_TEL4_BAUD, 57600);


/**
 * Serial Configuration for Secondary GPS
 *
 * Configure on which serial port to run Secondary GPS.
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group GPS
 * @reboot_required true
 */
PARAM_DEFINE_INT32(GPS_2_CONFIG, 0);

/**
 * Serial Configuration for Main GPS
 *
 * Configure on which serial port to run Main GPS.
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group GPS
 * @reboot_required true
 */
PARAM_DEFINE_INT32(GPS_1_CONFIG, 201);

/**
 * Serial Configuration for VectorNav (VN-100, VN-200, VN-300)
 *
 * Configure on which serial port to run VectorNav (VN-100, VN-200, VN-300).
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group Sensors
 * @reboot_required true
 */
PARAM_DEFINE_INT32(SENS_VN_CFG, 0);

/**
 * Serial Configuration for MAVLink (instance 0)
 *
 * Configure on which serial port to run MAVLink.
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group MAVLink
 * @reboot_required true
 */
PARAM_DEFINE_INT32(MAV_0_CONFIG, 101);

/**
 * Serial Configuration for MAVLink (instance 1)
 *
 * Configure on which serial port to run MAVLink.
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group MAVLink
 * @reboot_required true
 */
PARAM_DEFINE_INT32(MAV_1_CONFIG, 0);

/**
 * Serial Configuration for MAVLink (instance 2)
 *
 * Configure on which serial port to run MAVLink.
 *
 * 
 *
 * @value 0 Disabled
 * @value 201 GPS 1
 * @value 101 TELEM 1
 * @value 102 TELEM 2
 * @value 104 TELEM/SERIAL 4
 * @group MAVLink
 * @reboot_required true
 */
PARAM_DEFINE_INT32(MAV_2_CONFIG, 0);

