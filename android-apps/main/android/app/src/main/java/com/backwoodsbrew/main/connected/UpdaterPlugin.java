package com.backwoodsbrew.main.connected;
import android.content.Intent;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
@CapacitorPlugin(name="BackwoodsUpdater")
public class UpdaterPlugin extends Plugin {
    @PluginMethod public void open(PluginCall call){
        getActivity().runOnUiThread(()->getActivity().startActivity(new Intent(getActivity(),com.backwoodsbrew.updates.UpdaterActivity.class)));call.resolve();
    }
}
