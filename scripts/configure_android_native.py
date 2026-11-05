"""Apply deterministic metadata and permissions after `cap add android`."""
import json
from pathlib import Path
import re
from prepare_app_icons import prepare_icons

ROOT=Path(__file__).resolve().parents[1]
GRADLE_SHA256='f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6'


def configure():
    for kind in ['main','vendor']:
        project=ROOT/'android-apps'/kind
        metadata=json.loads((project/'build-metadata.json').read_text())
        android=project/'android'
        build=android/'app/build.gradle'
        text=build.read_text()
        text=re.sub(r'versionCode \d+','versionCode '+str(metadata['versionCode']),text,count=1)
        text=re.sub(r'versionName [\'"][^\'"]+[\'"]','versionName "'+metadata['versionName']+'"',text,count=1)
        build.write_text(text)
        wrapper=android/'gradle/wrapper/gradle-wrapper.properties'
        text=wrapper.read_text().replace('gradle-8.11.1-all.zip','gradle-8.11.1-bin.zip')
        if 'distributionSha256Sum=' not in text:text+='\ndistributionSha256Sum='+GRADLE_SHA256+'\n'
        wrapper.write_text(text)
        manifest=android/'app/src/main/AndroidManifest.xml'
        text=manifest.read_text().replace('android:allowBackup="true"','android:allowBackup="false"')
        for permission in ['CAMERA','ACCESS_COARSE_LOCATION','ACCESS_FINE_LOCATION']:
            tag=f'<uses-permission android:name="android.permission.{permission}" />'
            if tag not in text:text=text.replace('</manifest>','    '+tag+'\n</manifest>')
        camera='<uses-feature android:name="android.hardware.camera" android:required="false" />'
        if camera not in text:text=text.replace('</manifest>','    '+camera+'\n</manifest>')
        manifest.write_text(text)
        resources=android/'app/src/main/res'
        prepare_icons(kind)
        for splash in resources.glob('**/splash.png'):splash.unlink()
        (resources/'drawable/splash.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@color/backwoods_splash" />
    <item android:width="96dp" android:height="96dp" android:gravity="center" android:drawable="@mipmap/ic_launcher_foreground" />
</layer-list>
''')
        (resources/'values/backwoods_colors.xml').write_text('<resources><color name="backwoods_splash">#153e35</color></resources>\n')
        styles=resources/'values/styles.xml'
        styles.write_text(re.sub(r'<style name="AppTheme.NoActionBarLaunch"[^>]*>[\s\S]*?</style>',
            '<style name="AppTheme.NoActionBarLaunch" parent="Theme.SplashScreen">\n'
            '        <item name="android:background">@drawable/splash</item>\n'
            '        <item name="windowSplashScreenBackground">@color/backwoods_splash</item>\n'
            '        <item name="windowSplashScreenAnimatedIcon">@mipmap/ic_launcher_foreground</item>\n'
            '        <item name="postSplashScreenTheme">@style/AppTheme.NoActionBar</item>\n'
            '    </style>',styles.read_text(),count=1))
    print('Configured Android versions, verified Gradle distribution, company icons and required permissions.')


if __name__=='__main__':configure()
