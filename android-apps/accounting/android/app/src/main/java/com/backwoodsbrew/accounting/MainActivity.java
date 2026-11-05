package com.backwoodsbrew.accounting;

import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.print.PrintManager;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JsResult;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AlertDialog;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import androidx.appcompat.app.AppCompatActivity;

/** Company-ledger client. Never starts a second, unrelated ledger on the phone. */
public class MainActivity extends AppCompatActivity {
    private WebView browser;
    private String origin;

    private ValueCallback<Uri[]> fileCallback;
    private TextView status;
    private String downloadUrl,downloadCookies;
    private static final int SAVE_REQUEST=121;
    private static final int FILE_REQUEST = 120;
    private final int forest = Color.rgb(21,62,53);

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(forest);
        SecureStorage.initialize(getApplicationContext());
        origin=""; setup();
        com.backwoodsbrew.updates.UpdaterActivity.scheduleCheck(this);
    }

    private void copyProgramAssets() throws Exception {
        java.io.File directory=new java.io.File(getFilesDir(),"accounting-program/web");
        if(!directory.exists()&&!directory.mkdirs())throw new Exception("Could not prepare the accounting program.");
        for(String name:getAssets().list("accounting-web")){
            try(java.io.InputStream input=getAssets().open("accounting-web/"+name);java.io.OutputStream output=new java.io.FileOutputStream(new java.io.File(directory,name))){
                byte[] data=new byte[8192];int n;while((n=input.read(data))!=-1)output.write(data,0,n);
            }
        }
    }
    private boolean sameLocalOrigin(String value) {return EngineOrigin.contains(origin,value);}

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setFitsSystemWindows(true);
        layout.setBackgroundColor(Color.rgb(245,245,239));
        return layout;
    }
    private TextView text(String value, int size) {
        TextView label = new TextView(this); label.setText(value); label.setTextSize(size);
        label.setTextColor(forest); label.setPadding(0,dp(8),0,dp(12)); return label;
    }
    private Button button(String label, View.OnClickListener action) {
        Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setOnClickListener(action); return b;
    }

    private void setup() {
        LinearLayout layout=column();layout.setPadding(dp(24),dp(36),dp(24),dp(24));
        layout.addView(text("BACKWOODS",17));layout.addView(text("Business Accounting",29));
        layout.addView(text("Sign in to your company",21));
        layout.addView(text("Use the same owner Firebase login as your retail and wholesale apps. Your records sync through Firebase. No server or transfer link is needed.",16));
        EditText email=new EditText(this);email.setSingleLine(true);email.setHint("Firebase username or company email");
        email.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);layout.addView(email);
        EditText password=new EditText(this);password.setSingleLine(true);password.setHint("Password");
        password.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);layout.addView(password);
        TextView error=text("",14);layout.addView(error);
        Button connect=button("Sign in",null);
        connect.setOnClickListener(view->{
            final String address=email.getText().toString().trim(),secret=password.getText().toString();
            if(address.isEmpty()||secret.isEmpty()){error.setText("Enter your Firebase username or email and password.");return;}
            connect.setEnabled(false);error.setText("Signing in and finding your company books…");password.setText("");
            new Thread(()->{
                try{
                    copyProgramAssets();
                    if(!Python.isStarted())Python.start(new AndroidPlatform(getApplicationContext()));
                    Python python=Python.getInstance();
                    int port=python.getModule("android_boot").callAttr("start",getFilesDir().getAbsolutePath()).toInt();
                    JSONObject result=new JSONObject(python.getModule("android_boot").callAttr("sign_in",address,secret).toString());
                    final String local=EngineOrigin.local(port);
                    final String bootstrap=result.getString("bootstrap"),session=result.optString("sessionToken","");
                    runOnUiThread(()->{if(isDestroyed())return;origin=local;
                        CookieManager cookies=CookieManager.getInstance();cookies.setAcceptCookie(true);
                        cookies.setCookie(origin,"bw_bootstrap="+bootstrap+"; Path=/; HttpOnly; SameSite=Strict");
                        if(!session.isEmpty())cookies.setCookie(origin,"bw_session="+session+"; Path=/; HttpOnly; SameSite=Strict");
                        cookies.flush();openBooks();});
                }catch(Exception problem){runOnUiThread(()->{if(isDestroyed())return;error.setText(problem.getMessage()==null?"Cannot reach Firebase. Check your Internet connection.":problem.getMessage());connect.setEnabled(true);});}
            },"company-sign-in").start();
        });
        layout.addView(connect);
        Button cached=button("Open this device's saved books",null);
        cached.setOnClickListener(view->{
            cached.setEnabled(false);error.setText("Opening private cached books…");
            new Thread(()->{
                try{
                    copyProgramAssets();
                    if(!Python.isStarted())Python.start(new AndroidPlatform(getApplicationContext()));
                    Python python=Python.getInstance();
                    python.getModule("android_boot").callAttr("start",getFilesDir().getAbsolutePath());
                    JSONObject result=new JSONObject(python.getModule("android_boot").callAttr("local_books").toString());
                    final String local=EngineOrigin.local(result.getInt("port")),bootstrap=result.getString("bootstrap");
                    runOnUiThread(()->{if(isDestroyed())return;origin=local;CookieManager cookies=CookieManager.getInstance();cookies.setAcceptCookie(true);cookies.setCookie(origin,"bw_bootstrap="+bootstrap+"; Path=/; HttpOnly; SameSite=Strict");cookies.flush();openBooks();});
                }catch(Exception problem){runOnUiThread(()->{if(isDestroyed())return;error.setText(problem.getMessage());cached.setEnabled(true);});}
            },"cached-accounting").start();
        });
        layout.addView(cached);
        layout.addView(button("App updates",v->startActivity(new Intent(this,com.backwoodsbrew.updates.UpdaterActivity.class))));
        layout.addView(text("Your records stay together",18));
        layout.addView(text("Retail and wholesale keep their own books. Business Accounting combines their accounting records with payroll, production costs and business expenses. The first accounting sign-in may ask you to create your business owner account. Firebase permissions must be enabled once for your company.",14));
        android.widget.ScrollView scroll=new android.widget.ScrollView(this);scroll.setFillViewport(true);scroll.setFitsSystemWindows(true);scroll.addView(layout);setContentView(scroll);
    }

    @SuppressWarnings("SetJavaScriptEnabled") private void openBooks() {
        LinearLayout layout = column();
        LinearLayout bar = new LinearLayout(this);
        bar.addView(button("Books", v -> browser.loadUrl(origin + "/")));
        bar.addView(button("Print", v -> print()));
        bar.addView(button("Updates",v->startActivity(new Intent(this,com.backwoodsbrew.updates.UpdaterActivity.class))));
        bar.addView(button("Company account", v -> new AlertDialog.Builder(this)
            .setTitle("Sign in to another company?")
            .setMessage("This signs you out on this phone and clears its cached web data. Company records stay in Firebase and this app's private data. A different company requires a separate app profile.")
            .setNegativeButton("Cancel",null).setPositiveButton("Change",(d,w) -> {
                browser.stopLoading(); browser.loadUrl("about:blank"); browser.clearCache(true);
                browser.clearHistory(); browser.destroy(); browser = null;
                WebStorage.getInstance().deleteAllData();
                CookieManager.getInstance().removeAllCookies(done -> {
                    CookieManager.getInstance().flush();
                    getPreferences(MODE_PRIVATE).edit().remove("firebase_company_origin").apply(); setup();
                });
            }).show()));
        layout.addView(bar);
        status = text("Opening company books…",12); status.setPadding(dp(12),0,dp(12),dp(4)); layout.addView(status);
        browser = new WebView(this);
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        // ACTION_OPEN_DOCUMENT supplies content URIs selected by the user.
        // No broad storage permission or JavaScript filesystem bridge is exposed.
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setSupportMultipleWindows(false); settings.setJavaScriptCanOpenWindowsAutomatically(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser,false);
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (sameLocalOrigin(url)) return false;
                if ("https".equalsIgnoreCase(request.getUrl().getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,request.getUrl())); }
                    catch (ActivityNotFoundException e) { message("No browser is available."); }
                } else message("Only secure company pages can open here.");
                return true;
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel(); status.setText("A secure connection could not be verified.");
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) status.setText("Could not open the embedded accounting engine. Reopen the app; your private cached records are preserved.");
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (sameLocalOrigin(url)) {
                    status.setText("Company books · Firebase sync · Print / PDF");

                }
            }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onJsAlert(WebView view,String url,String message,JsResult result) {
                if (!sameLocalOrigin(url)) { result.cancel(); return true; }
                new AlertDialog.Builder(MainActivity.this).setMessage(message)
                    .setPositiveButton("OK",(d,w) -> result.confirm())
                    .setOnCancelListener(d -> result.cancel()).show();
                return true;
            }
            @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result) {
                if (!sameLocalOrigin(url)) { result.cancel(); return true; }
                new AlertDialog.Builder(MainActivity.this).setMessage(message)
                    .setPositiveButton("Confirm",(d,w) -> result.confirm())
                    .setNegativeButton("Cancel",(d,w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel()).show();
                return true;
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);
                try { startActivityForResult(intent,FILE_REQUEST); }
                catch (ActivityNotFoundException error) { fileCallback.onReceiveValue(null); fileCallback=null; return false; }
                return true;
            }
        });
        browser.setDownloadListener((url,agent,disposition,mime,length) -> {
            if(!sameLocalOrigin(url)){message("Download blocked: outside this accounting app.");return;}
            downloadUrl=url;downloadCookies=CookieManager.getInstance().getCookie(url);
            Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(mime==null?"application/octet-stream":mime)
                .putExtra(Intent.EXTRA_TITLE,android.webkit.URLUtil.guessFileName(url,disposition,mime));
            try{startActivityForResult(save,SAVE_REQUEST);}catch(ActivityNotFoundException error){message("No file-saving app is available. Use Print to save a PDF.");downloadUrl=null;downloadCookies=null;}
        });
        layout.addView(browser,new LinearLayout.LayoutParams(-1,0,1)); setContentView(layout);
        browser.loadUrl(origin + "/");
    }

    private void print() {
        if (browser == null || !sameLocalOrigin(browser.getUrl())) { message("Open a company record first."); return; }
        PrintManager manager = (PrintManager)getSystemService(PRINT_SERVICE);
        manager.print("Backwoods company record",browser.createPrintDocumentAdapter("Backwoods company record"),null);
    }
    private void message(String value) { Toast.makeText(this,value,Toast.LENGTH_LONG).show(); }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==SAVE_REQUEST){
            final String url=downloadUrl,cookies=downloadCookies;downloadUrl=null;downloadCookies=null;
            if(result!=RESULT_OK||data==null||data.getData()==null||url==null)return;
            final Uri destination=data.getData();
            new Thread(()->{
                java.net.HttpURLConnection connection=null;
                try{
                    if(!sameLocalOrigin(url))throw new Exception("The company account changed before the download.");
                    connection=(java.net.HttpURLConnection)new java.net.URL(url).openConnection();
                    connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(60000);
                    if(cookies!=null)connection.setRequestProperty("Cookie",cookies);
                    if(connection.getResponseCode()!=200)throw new Exception("Download not authorized. Sign in and try again.");
                    try(java.io.InputStream input=connection.getInputStream();java.io.OutputStream output=getContentResolver().openOutputStream(destination)){
                        if(output==null)throw new Exception("Could not open the chosen file destination.");
                        byte[] buffer=new byte[16384];int n;while((n=input.read(buffer))!=-1)output.write(buffer,0,n);
                    }
                    runOnUiThread(()->message("Company record saved."));
                }catch(Exception error){runOnUiThread(()->message(error.getMessage()));}
                finally{if(connection!=null)connection.disconnect();}
            },"save-accounting-record").start();
            return;
        }
        if (request == FILE_REQUEST && fileCallback != null) {
            fileCallback.onReceiveValue(result == RESULT_OK && data != null && data.getData() != null ? new Uri[]{data.getData()} : null);
            fileCallback = null;
        }
    }
    @Override public void onBackPressed() {
        if (browser != null && browser.canGoBack()) browser.goBack(); else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) { fileCallback.onReceiveValue(null); fileCallback = null; }
        if (browser != null) { browser.destroy(); browser=null; }
        super.onDestroy();
    }
}
