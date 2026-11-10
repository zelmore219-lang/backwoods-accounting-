package com.backwoodsbrew.main.connected;

import android.content.Context;
import android.print.PrintAttributes;
import android.print.PrintManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Android system printer selection for the rendered in-app receipt. */
@CapacitorPlugin(name = "NativePrint")
public final class NativePrintPlugin extends Plugin {
    @PluginMethod public void print(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                PrintManager manager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                if (manager == null) { call.reject("Android printing is unavailable on this device."); return; }
                manager.print("Backwoods Brew receipt", getBridge().getWebView().createPrintDocumentAdapter("Backwoods Brew receipt"),
                    new PrintAttributes.Builder().setMinMargins(PrintAttributes.Margins.NO_MARGINS).build());
                call.resolve();
            } catch (Exception error) { call.reject("Could not open print options: " + error.getMessage()); }
        });
    }
}
