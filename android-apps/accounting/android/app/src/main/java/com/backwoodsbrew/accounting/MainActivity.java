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
import androidx.appcompat.app.AppCompatActivity;

/** Company-ledger client. Never starts a second, unrelated ledger on the phone. */
public class MainActivity extends AppCompatActivity {
    private WebView browser;
    private String origin;
    private String pendingFirebaseToken;
    private ValueCallback<Uri[]> fileCallback;
    private TextView status;
    private static final int FILE_REQUEST = 120;
    private final int forest = Color.rgb(21,62,53);

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(forest);
        origin=""; setup();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
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
        layout.addView(text("Use the same owner Firebase account as your retail and wholesale apps. Your accounting connection is found automatically.",16));
        EditText email=new EditText(this);email.setSingleLine(true);email.setHint("Company email");
        email.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);layout.addView(email);
        EditText password=new EditText(this);password.setSingleLine(true);password.setHint("Password");
        password.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);layout.addView(password);
        TextView error=text("",14);layout.addView(error);
        Button connect=button("Sign in",null);
        connect.setOnClickListener(view->{
            final String address=email.getText().toString().trim(),secret=password.getText().toString();
            if(address.isEmpty()||secret.isEmpty()){error.setText("Enter your company email and password.");return;}
            connect.setEnabled(false);error.setText("Signing in and finding your company books…");password.setText("");
            new Thread(()->{
                try{
                    FirebaseDiscovery.Company company=FirebaseDiscovery.signIn(address,secret);
                    runOnUiThread(()->{if(isDestroyed())return;origin=company.origin;pendingFirebaseToken=company.idToken;
                        getPreferences(MODE_PRIVATE).edit().putString("firebase_company_origin",origin).apply();openBooks();});
                }catch(Exception problem){runOnUiThread(()->{if(isDestroyed())return;error.setText(problem.getMessage()==null?"Cannot reach Firebase. Check your Internet connection.":problem.getMessage());connect.setEnabled(true);});}
            },"company-sign-in").start();
        });
        layout.addView(connect);
        layout.addView(text("Your records stay together",18));
        layout.addView(text("Retail and wholesale keep their own books. Business Accounting combines their accounting records with payroll, production costs and business expenses. Your administrator must complete the one-time company cloud setup before the first connection.",14));
        setContentView(layout);
    }

    @SuppressWarnings("SetJavaScriptEnabled") private void openBooks() {
        LinearLayout layout = column();
        LinearLayout bar = new LinearLayout(this);
        bar.addView(button("Books", v -> browser.loadUrl(origin + "/")));
        bar.addView(button("Print", v -> print()));
        bar.addView(button("Company account", v -> new AlertDialog.Builder(this)
            .setTitle("Sign in to another company?")
            .setMessage("This signs you out on this phone and clears its cached web data. Company records stay on the accounting server.")
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
                if (CompanyOrigin.contains(origin,url)) return false;
                if ("https".equalsIgnoreCase(request.getUrl().getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,request.getUrl())); }
                    catch (ActivityNotFoundException e) { message("No browser is available."); }
                } else message("Only secure company pages can open here.");
                return true;
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel(); status.setText("Certificate check failed. Ask your administrator to fix the server certificate.");
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) status.setText("Cannot reach the company server. Check its address and your Internet connection.");
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (CompanyOrigin.contains(origin,url)) {
                    status.setText("Company books · Print saves PDF or sends to your printer");
                    if(pendingFirebaseToken!=null){
                        String encoded=org.json.JSONObject.quote(pendingFirebaseToken);pendingFirebaseToken=null;
                        view.evaluateJavascript("fetch('/api/auth/firebase-login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Accounting-Request':'1'},body:JSON.stringify({idToken:"+encoded+"})}).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.error||'Company login failed');location.reload();}).catch(e=>{document.body.textContent=e.message;})",null);
                    }
                }
            }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onJsAlert(WebView view,String url,String message,JsResult result) {
                if (!CompanyOrigin.contains(origin,url)) { result.cancel(); return true; }
                new AlertDialog.Builder(MainActivity.this).setMessage(message)
                    .setPositiveButton("OK",(d,w) -> result.confirm())
                    .setOnCancelListener(d -> result.cancel()).show();
                return true;
            }
            @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result) {
                if (!CompanyOrigin.contains(origin,url)) { result.cancel(); return true; }
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
            if (!CompanyOrigin.contains(origin,url)) { message("Download blocked: different server."); return; }
            new AlertDialog.Builder(this).setTitle("Save company record?")
                .setMessage("This saves a copy in this phone's Downloads folder. Financial records may contain private information.")
                .setNegativeButton("Cancel",null).setPositiveButton("Save",(dialog,which) -> {
                    try {
                        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                        String cookies = CookieManager.getInstance().getCookie(url);
                        if (cookies != null) request.addRequestHeader("Cookie",cookies);
                        request.addRequestHeader("User-Agent",agent);
                        request.setMimeType(mime);
                        String name = android.webkit.URLUtil.guessFileName(url,disposition,mime);
                        request.setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS,name);
                        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                        ((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
                        message("Download started.");
                    } catch (RuntimeException error) { message("Download unavailable. Print to PDF or use your secure browser."); }
                }).show();
        });
        layout.addView(browser,new LinearLayout.LayoutParams(-1,0,1)); setContentView(layout);
        browser.loadUrl(origin + "/");
    }

    private void print() {
        if (browser == null || !CompanyOrigin.contains(origin,browser.getUrl())) { message("Open a company record first."); return; }
        PrintManager manager = (PrintManager)getSystemService(PRINT_SERVICE);
        manager.print("Backwoods company record",browser.createPrintDocumentAdapter("Backwoods company record"),null);
    }
    private void message(String value) { Toast.makeText(this,value,Toast.LENGTH_LONG).show(); }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
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
