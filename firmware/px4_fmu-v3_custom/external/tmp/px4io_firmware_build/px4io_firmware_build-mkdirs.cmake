# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Source/px4io_firmware_build")
  file(MAKE_DIRECTORY "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Source/px4io_firmware_build")
endif()
file(MAKE_DIRECTORY
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Build/px4io_firmware_build"
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Install/px4io_firmware_build"
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/tmp/px4io_firmware_build"
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Stamp/px4io_firmware_build"
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Download/px4io_firmware_build"
  "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Stamp/px4io_firmware_build"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Stamp/px4io_firmware_build/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/osmancevik/PX4-Autopilot/build/px4_fmu-v3_default/external/Stamp/px4io_firmware_build${cfgdir}") # cfgdir has leading slash
endif()
