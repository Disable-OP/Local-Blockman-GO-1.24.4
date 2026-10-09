# GameServer on-device build — arm64, gcc 4.9 + gnustl (era-matched)
APP_ABI := arm64-v8a
APP_PLATFORM := android-21
APP_STL := gnustl_static
NDK_TOOLCHAIN_VERSION := 4.9
APP_CPPFLAGS := -std=c++11 -frtti -fexceptions -pthread -D_FORCE_INLINES
APP_OPTIM := release
APP_MODULES := gameserver
