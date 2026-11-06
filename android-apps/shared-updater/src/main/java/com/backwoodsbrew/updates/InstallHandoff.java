package com.backwoodsbrew.updates;

import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import androidx.core.content.FileProvider;
import java.io.File;

public final class InstallHandoff {
    private InstallHandoff() {}

    public static Intent intent(Context context, File apk) {
        Uri uri=FileProvider.getUriForFile(context,context.getPackageName()+".updates",apk);
        Intent intent=new Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri,"application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.setClipData(ClipData.newRawUri("Verified app update",uri));
        return intent;
    }
}
