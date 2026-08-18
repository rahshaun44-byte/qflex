cmake_minimum_required(VERSION 3.20)
project(QuantumFlex)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SYSTEMD REQUIRED libsystemd)
find_package(OpenSSL REQUIRED)

# Sentinel Push Client Executable
add_executable(sentinel_push sentinel_push.cpp)
target_include_directories(sentinel_push PRIVATE ${SYSTEMD_INCLUDE_DIRS} ${OPENSSL_INCLUDE_DIR})
target_link_libraries(sentinel_push PRIVATE ${SYSTEMD_LIBRARIES} OpenSSL::SSL OpenSSL::Crypto)
