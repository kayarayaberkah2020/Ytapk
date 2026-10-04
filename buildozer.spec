[app]
title = PyIDE
package.name = pyide
package.domain = org.pyide

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 0.1

# Library Python yang ikut dibundel ke APK.
# Tambah library lain di sini (dipisah koma) sebelum build.
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,pygments

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

# Kunci versi python-for-android agar tidak memakai Python 3.14
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
