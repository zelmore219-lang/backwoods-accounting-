package com.backwoodsbrew.main.connected;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle saved){registerPlugin(UpdaterPlugin.class);super.onCreate(saved);com.backwoodsbrew.updates.UpdaterActivity.scheduleCheck(this);}
}
