[app]
title = PyIDE
package.name = pyide
package.domain = org.pyide

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 0.1

# Library Python yang ikut dibundel ke APK.
# Tambah library lain di sini (dipisah koma) sebelum build.
requirements = python3,kivy==2.3.0,pygments

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
