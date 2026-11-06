package com.backwoodsbrew.updates;

import static org.junit.Assert.*;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ProviderInfo;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=35)
public class InstallHandoffTest {
    @Test public void installerReceivesReadableApkFromSeparateProvider() throws Exception {
        Context context=RuntimeEnvironment.getApplication();
        String authority=context.getPackageName()+".updates";
        ProviderInfo updater=context.getPackageManager().resolveContentProvider(authority,0);
        ProviderInfo capacitor=context.getPackageManager().resolveContentProvider(context.getPackageName()+".fileprovider",0);
        assertNotNull(updater);assertEquals(UpdateFileProvider.class.getName(),updater.name);
        // Android identifies local providers by component class. Reusing the
        // Capacitor class for a second authority can leave it unregistered.
        if(capacitor!=null)assertNotEquals(capacitor.name,updater.name);
        Robolectric.buildContentProvider(UpdateFileProvider.class).create(updater).get();
        File directory=new File(context.getCacheDir(),"updates");directory.mkdirs();
        File apk=new File(directory,"verified.apk");
        byte[] expected="verified APK fixture".getBytes(StandardCharsets.UTF_8);
        Files.write(apk.toPath(),expected);
        Intent intent=InstallHandoff.intent(context,apk);
        assertEquals(Intent.ACTION_VIEW,intent.getAction());
        assertEquals("application/vnd.android.package-archive",intent.getType());
        assertEquals("content",intent.getData().getScheme());
        assertEquals(authority,intent.getData().getAuthority());
        assertEquals(intent.getData(),intent.getClipData().getItemAt(0).getUri());
        assertTrue((intent.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0);
        try(java.io.InputStream input=context.getContentResolver().openInputStream(intent.getData())) {
            assertArrayEquals(expected,input.readAllBytes());
        }
    }

    @Test public void providerRejectsFilesOutsideVerifiedUpdateDirectory() throws Exception {
        Context context=RuntimeEnvironment.getApplication();
        File privateFile=new File(context.getFilesDir(),"company-records.db");
        Files.write(privateFile.toPath(),new byte[]{1});
        assertThrows(IllegalArgumentException.class,()->InstallHandoff.intent(context,privateFile));
    }
}
