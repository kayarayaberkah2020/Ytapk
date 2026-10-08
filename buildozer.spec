[app]
title = YUTUFY
package.name = yutufy
package.domain = org.ridho
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0

requirements = python3,kivy==2.3.0,pyjnius,yt-dlp,certifi,openssl,requests,urllib3,idna
android.archs = arm64-v8a

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, WAKE_LOCK, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE
android.api = 33
android.minapi = 24

android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1