package com.backwoodsbrew.updates;

import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.view.View;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.app.AlertDialog;
import androidx.core.content.FileProvider;
import org.json.JSONObject;
import java.io.*;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.lang.ref.WeakReference;

/** Native updater: verified GitHub downloads, explicit OS install confirmation. */
public class UpdaterActivity extends AppCompatActivity {
    private static final AtomicBoolean BUSY=new AtomicBoolean();
    private static WeakReference<UpdaterActivity> visible=new WeakReference<>(null);
    private static String phase="idle",message="Ready to check for updates.";
    private static int percent;
    private TextView status,current,latest;
    private EditText feed;
    private CheckBox enabled,automatic;
    private Button save,check,download,install;
    private ProgressBar progress;
    private static SharedPreferences prefs(android.content.Context c){return c.getSharedPreferences("backwoods-app-updates",MODE_PRIVATE);}
    private static String kind(android.content.Context c){String p=c.getPackageName();return p.endsWith("accounting")?"accounting":p.contains("vendor")?"vendor":"main";}
    private static PackageInfo installed(android.content.Context c)throws Exception{return c.getPackageManager().getPackageInfo(c.getPackageName(),Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES);}
    private static long code(PackageInfo p){return Build.VERSION.SDK_INT>=28?p.getLongVersionCode():p.versionCode;}
    private static Set<String> certificates(PackageInfo p)throws Exception{
        Signature[] signatures=Build.VERSION.SDK_INT>=28?(p.signingInfo==null?null:p.signingInfo.getApkContentsSigners()):p.signatures;
        if(signatures==null||signatures.length==0)throw new Exception("The app signing certificate could not be verified.");
        Set<String> result=new HashSet<>();for(Signature s:signatures)result.add(hex(MessageDigest.getInstance("SHA-256").digest(s.toByteArray())));return result;
    }
    private static String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
    private static void state(String p,String text){phase=p;message=text;UpdaterActivity a=visible.get();if(a!=null)a.runOnUiThread(a::refresh);}
    private static HttpsURLConnection connection(String address)throws Exception{
        for(int i=0;i<6;i++){
            UpdatePolicy.redirect(address);HttpsURLConnection c=(HttpsURLConnection)new URL(address).openConnection();
            c.setConnectTimeout(20000);c.setReadTimeout(60000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","Backwoods-App-Updater");
            int status=c.getResponseCode();
            if(status==301||status==302||status==303||status==307||status==308){String location=c.getHeaderField("Location");c.disconnect();if(location==null)throw new Exception("Invalid update redirect");address=new URL(new URL(address),location).toString();continue;}
            if(status!=200){c.disconnect();throw new Exception(status==404?"The update feed has not been published yet.":"Update server returned HTTP "+status);}
            return c;
        }
        throw new Exception("Too many update redirects");
    }
    private static JSONObject checkFeed(android.content.Context c)throws Exception{
        String address=UpdatePolicy.trusted(prefs(c).getString("feed",UpdatePolicy.FEED));
        HttpsURLConnection connection=connection(address);ByteArrayOutputStream out=new ByteArrayOutputStream();
        try(InputStream input=connection.getInputStream()){byte[] b=new byte[8192];int n;while((n=input.read(b))!=-1){if(out.size()+n>1024*1024)throw new Exception("Update feed is too large");out.write(b,0,n);}}finally{connection.disconnect();}
        JSONObject manifest=new JSONObject(out.toString("UTF-8"));if(manifest.getInt("schemaVersion")!=1)throw new Exception("Unsupported update feed");
        JSONObject info=manifest.getJSONObject("apps").getJSONObject(kind(c)).getJSONObject("android");
        validate(c,info);
        SharedPreferences.Editor editor=prefs(c).edit().putString("latest",info.toString()).putLong("lastCheck",System.currentTimeMillis());
        String saved=prefs(c).getString("downloaded","");if(!saved.isEmpty()&&!new JSONObject(saved).optString("sha256").equals(info.getString("sha256")))editor.remove("downloaded");
        editor.apply();return info;
    }
    private static void validate(android.content.Context c,JSONObject info)throws Exception{
        UpdatePolicy.newer(info.getString("version"),installed(c).versionName);UpdatePolicy.trusted(info.getString("url"));
        long size=info.getLong("size");
        if(!info.getString("url").endsWith(".apk")||!info.getString("packageName").equals(c.getPackageName())||size<2||size>1024L*1024*1024||!UpdatePolicy.digest(info.getString("sha256"))||!UpdatePolicy.digest(info.getString("certificateSha256")))throw new Exception("Invalid Android update details or wrong app.");
        if(!certificates(installed(c)).contains(info.getString("certificateSha256")))throw new Exception("This update uses a different signing key. Keep your installed app and data; an update signed with the original key is required.");
        if(info.getInt("minSdk")>Build.VERSION.SDK_INT)throw new Exception("This update requires a newer Android version.");
        boolean abi=false;for(String device:Build.SUPPORTED_ABIS)for(int i=0;i<info.getJSONArray("abis").length();i++)if(device.equals(info.getJSONArray("abis").getString(i)))abi=true;
        if(!abi)throw new Exception("This update does not support this device's processor.");
    }
    private static boolean available(android.content.Context c,JSONObject info)throws Exception{return info.getLong("versionCode")>code(installed(c))&&UpdatePolicy.newer(info.getString("version"),installed(c).versionName);}
    private static File apk(android.content.Context c,JSONObject info)throws Exception{
        String digest=info.getString("sha256");if(!UpdatePolicy.digest(digest)||info.getLong("versionCode")<=0)throw new Exception("Invalid cached update identity");
        return new File(c.getCacheDir(),"updates/update-"+info.getLong("versionCode")+"-"+digest+".apk");
    }
    private static File apk(android.content.Context c){try{return apk(c,new JSONObject(prefs(c).getString("downloaded","{}")));}catch(Exception e){return new File(c.getCacheDir(),"updates/no-update");}}
    private static void verify(android.content.Context c,JSONObject info,File file)throws Exception{
        validate(c,info);if(!available(c,info))throw new Exception("This is not a newer app version.");
        if(!file.isFile()||file.length()!=info.getLong("size"))throw new Exception("Download the complete update first.");
        MessageDigest digest=MessageDigest.getInstance("SHA-256");try(InputStream input=new FileInputStream(file)){byte[] data=new byte[65536];int n;while((n=input.read(data))!=-1)digest.update(data,0,n);}
        if(!hex(digest.digest()).equals(info.getString("sha256")))throw new Exception("Update checksum mismatch. Installation was blocked.");
        PackageInfo candidate=c.getPackageManager().getPackageArchiveInfo(file.getAbsolutePath(),Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES);
        if(candidate==null||!candidate.packageName.equals(c.getPackageName())||code(candidate)!=info.getLong("versionCode")||!info.getString("version").equals(candidate.versionName)||!certificates(candidate).equals(certificates(installed(c))))throw new Exception("The APK identity, version or signing certificate does not match. Installation was blocked.");
    }
    private static void get(android.content.Context c,JSONObject info)throws Exception{
        validate(c,info);if(!available(c,info))throw new Exception("Check for a newer version first.");
        File target=apk(c,info),part=new File(target.getPath()+".part");if(!target.getParentFile().isDirectory()&&!target.getParentFile().mkdirs())throw new Exception("Cannot prepare update storage.");
        if(target.getParentFile().getUsableSpace()<info.getLong("size")+20*1024*1024)throw new Exception("Not enough free space to download this update.");
        state("downloading","Downloading and verifying update…");percent=0;HttpsURLConnection conn=connection(info.getString("url"));
        try{try(InputStream in=conn.getInputStream();OutputStream out=new FileOutputStream(part)){byte[] data=new byte[65536];int n,previous=-1;long count=0;while((n=in.read(data))!=-1){count+=n;if(count>info.getLong("size"))throw new Exception("Update download exceeds its declared size.");out.write(data,0,n);percent=(int)(count*100/info.getLong("size"));if(percent!=previous){previous=percent;state("downloading","Downloading and verifying update… "+percent+"%");}}}
            verify(c,info,part);if(target.exists()&&!target.delete())throw new Exception("Cannot replace previous update download.");if(!part.renameTo(target))throw new Exception("Cannot save the verified update.");
            prefs(c).edit().putString("downloaded",info.toString()).apply();state("downloaded","Update verified. Choose Install when you are ready.");
        }finally{conn.disconnect();if(part.exists())part.delete();}
    }
    private interface Work{void run()throws Exception;}
    private static void work(Work action){if(!BUSY.compareAndSet(false,true))return;new Thread(()->{try{action.run();}catch(Exception e){state("error",e.getMessage()==null?"The update operation failed.":e.getMessage());}finally{BUSY.set(false);UpdaterActivity a=visible.get();if(a!=null)a.runOnUiThread(a::refresh);}},"app-updater").start();}
    public static void scheduleCheck(android.app.Activity owner){
        android.content.Context context=owner.getApplicationContext();SharedPreferences p=prefs(context);
        if(!p.getBoolean("enabled",true)||System.currentTimeMillis()-p.getLong("attempt",0)<6*60*60*1000)return;
        new Handler(android.os.Looper.getMainLooper()).postDelayed(()->{
            if(owner.isFinishing()||owner.isDestroyed())return;
            work(()->{p.edit().putLong("attempt",System.currentTimeMillis()).apply();state("checking","Checking for updates…");JSONObject info=checkFeed(context);boolean newer=available(context,info);
                state(newer?"available":"current",newer?"A new version is available.":"You have the latest published version.");
                if(newer&&p.getBoolean("auto",false))get(context,info);
                if(newer)owner.runOnUiThread(()->{if(!owner.isFinishing()&&!owner.isDestroyed()&&visible.get()==null)new AlertDialog.Builder((AppCompatActivity)owner).setTitle("App update available").setMessage("Version "+info.optString("version")+" is available. Save your work and open Updates when ready.").setNegativeButton("Later",null).setPositiveButton("Open updates",(d,w)->owner.startActivity(new Intent(owner,UpdaterActivity.class))).show();});
            });
        },12000);
    }
    private TextView label(String text,int size){TextView t=new TextView(this);t.setText(text);t.setTextSize(size);t.setTextColor(0xff153e35);t.setPadding(0,12,0,12);return t;}
    private Button button(LinearLayout root,String text,View.OnClickListener action){Button b=new Button(this);b.setText(text);b.setAllCaps(false);b.setOnClickListener(action);root.addView(b);return b;}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);setTitle("App updates");visible=new WeakReference<>(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(28,24,28,32);root.setBackgroundColor(0xfff5f5ef);
        root.addView(label("Auto Update",27));root.addView(label("Keep your app current. Company records stay in this app.",15));
        current=label("",17);root.addView(current);latest=label("",17);root.addView(latest);status=label("",15);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);root.addView(status);
        feed=new EditText(this);feed.setHint("Update feed");feed.setSingleLine(true);feed.setText(prefs(this).getString("feed",UpdatePolicy.FEED));root.addView(feed);
        enabled=new CheckBox(this);enabled.setText("Enabled");enabled.setChecked(prefs(this).getBoolean("enabled",true));root.addView(enabled);
        automatic=new CheckBox(this);automatic.setText("Auto-download (may use mobile data)");automatic.setChecked(prefs(this).getBoolean("auto",false));root.addView(automatic);
        save=button(root,"Save feed",v->{try{String url=UpdatePolicy.trusted(feed.getText().toString().trim());prefs(this).edit().putString("feed",url).putBoolean("enabled",enabled.isChecked()).putBoolean("auto",automatic.isChecked()).remove("latest").remove("downloaded").apply();state("idle","Update settings saved.");}catch(Exception e){state("error",e.getMessage());}});
        check=button(root,"Check",v->work(()->{if(!prefs(this).getBoolean("enabled",true)){state("disabled","Update checks are disabled.");return;}state("checking","Checking for updates…");JSONObject info=checkFeed(this);boolean newer=available(this,info);state(newer?"available":"current",newer?"A new version is available.":"You have the latest published version.");if(newer&&prefs(this).getBoolean("auto",false))get(this,info);}));
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);root.addView(progress);
        download=button(root,"Download",v->work(()->get(this,new JSONObject(prefs(this).getString("latest","{}")))));
        install=button(root,"Install",v->install());
        root.addView(label("Checks run when you open the app, at most once every six hours. Installation always needs your approval. Back up and save your work first. Android may ask you to allow updates from this app. Never uninstall to resolve a signing conflict.",14));
        ScrollView scroll=new ScrollView(this);scroll.addView(root);setContentView(scroll);refresh();
    }
    private void refresh(){if(isDestroyed()||isFinishing())return;try{current.setText("Current: "+installed(this).versionName);JSONObject info=new JSONObject(prefs(this).getString("latest","{}"));latest.setText("Latest: "+info.optString("version","Not checked"));}catch(Exception e){latest.setText("Latest: not checked");}status.setText(phase+" · "+message);boolean busy=BUSY.get();for(View v:new View[]{save,check,feed,enabled,automatic})v.setEnabled(!busy);download.setEnabled(!busy&&phase.equals("available"));boolean pending=false;try{pending=apk(this).isFile()&&available(this,new JSONObject(prefs(this).getString("downloaded","{}")));}catch(Exception ignored){}install.setEnabled(!busy&&pending);progress.setVisibility(phase.equals("downloading")?View.VISIBLE:View.GONE);progress.setProgress(percent);}
    private void install(){
        work(()->{JSONObject info=new JSONObject(prefs(this).getString("downloaded","{}"));verify(this,info,apk(this));runOnUiThread(()->{
            if(isDestroyed()||isFinishing())return;
            if(Build.VERSION.SDK_INT>=26&&!getPackageManager().canRequestPackageInstalls()){
                new AlertDialog.Builder(this).setTitle("Allow this app to install updates").setMessage("Open Android settings and allow updates from this app, then return and tap Install again.").setNegativeButton("Cancel",null).setPositiveButton("Open settings",(d,w)->startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())))).show();return;
            }
            new AlertDialog.Builder(this).setTitle("Install verified update?").setMessage("Save your work and back up your records. Android will ask you to confirm the update. Existing app data is preserved.").setNegativeButton("Later",null).setPositiveButton("Install",(d,w)->{
                try{Uri uri=FileProvider.getUriForFile(this,getPackageName()+".updates",apk(this));Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);startActivity(intent);state("installing","Complete the update in the Android installer.");}catch(Exception e){state("error","Android could not open the package installer. "+e.getMessage());}
            }).show();
        });});
    }
    @Override protected void onResume(){super.onResume();if(status!=null)refresh();}
    @Override protected void onDestroy(){if(visible.get()==this)visible.clear();super.onDestroy();}
}
