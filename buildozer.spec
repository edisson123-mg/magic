%%writefile buildozer.spec
[app]

# (str) Title of your application
title = MagicPump

# (str) Package name
package.name = magicpump

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (str) Source filename (default to main.py)
source.include_exts = py,png,jpg,kv,atlas,json

# (list) Application requirements
# NOTA: He incluido librerias críticas para redes y SSL
requirements = python3,kivy==2.2.1,requests,urllib3,chardet,idna,certifi,openssl,libffi

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivy = ../../kivy

# (str) Presplash of the application
# presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
# icon.filename = %(source.dir)s/data/icon.png

# (list) Supported orientations
# Valid options are: landscape, portrait, portrait-reverse or landscape-reverse
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET, WAKE_LOCK, ACCESS_NETWORK_STATE

# (int) Target Android API, should be as high as possible.
# Xiaomi 14c usa Android 13/14, así que usamos API 33.
android.api = 33
android.minapi = 24
android.sdk = 33
android.ndk = 25b
android.ndk_api = 24

# (bool) Use --private data storage (True) or --dir public storage (False)
android.private_storage = True

# (str) Android NDK version to use
android.ndk_path = /root/.buildozer/android/platform/android-ndk-r25b

# (bool) If True, then skip trying to update the Android sdk
# This can be useful to avoid excess Internet downloads or save time
# when an update is due and you just want to test/build your package
android.skip_update = False

# (bool) If True, then automatically accept SDK license
# agreements. This is intended for automation only. If set to False,
# the default, you will be shown the license when first running
# buildozer.
android.accept_sdk_license = True

# (str) The entry point of your application
android.entrypoint = org.kivy.android.PythonActivity

# (list) List of Java .jar files to add to the libs so that pyjnius can access
# their classes. Don't add jars that you do not need, since extra jars can slow
# down the build process. Allows wildcards matching, for example:
# OUYA-ODK/libs/*.jar
# android.add_jars = foo.jar,bar.jar,common/android.jar

# (list) List of Java files to add to the android project (can be java or a
# directory containing the files)
# android.add_src =

# (str) python-for-android branch to use, defaults to master
p4a.branch = master

# (str) OUYA Console category. Should be one of:
# GAME, APP_SYSTEM, APP_LIFESTYLE, APP_MEDIA, APP_OTHER
# android.ouya.category = GAME

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
# android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
# android.manifest.intent_filters =

# (list) Android AAR archives to add (currently works only with sdl2_gradle
# bootstrap)
# android.add_aars =

# (list) Gradle dependencies to add (currently works only with sdl2_gradle
# bootstrap)
# android.gradle_dependencies =

# (bool) Enable AndroidX support. Enable when 'android.gradle_dependencies'
# contains an 'androidx' package, or any package that depends on AndroidX.
# android.enable_androidx = True

# (list) Java classes to add as activities to the manifest.
# android.add_activities = com.example.ExampleActivity

# (str) Python source code to compile to
# p4a.source_dir =

# (list) The architectures to build for, the default is armeabi-v7a.
# Xiaomi 14c es arm64-v8a.
android.archs = arm64-v8a

# (bool) enables / disables the splash screen
android.enable_splash = True

# (str) The background color of the splash screen
android.splash_color = 000000

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 0
