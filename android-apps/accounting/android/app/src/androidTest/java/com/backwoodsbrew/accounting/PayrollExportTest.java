package com.backwoodsbrew.accounting;

import static org.junit.Assert.*;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.webkit.CookieManager;
import android.webkit.WebView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Real Android Python, SQLite, WebView, authorized export and native save picker. */
@RunWith(AndroidJUnit4.class)
public class PayrollExportTest {
 private final Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
 private String js(WebView web,String code)throws Exception{
  CountDownLatch done=new CountDownLatch(1);AtomicReference<String> result=new AtomicReference<>();
  instrumentation.runOnMainSync(()->web.evaluateJavascript(code,value->{result.set(value);done.countDown();}));
  assertTrue("WebView JavaScript timed out",done.await(15,TimeUnit.SECONDS));return result.get();
 }
 private void ready(WebView web,String condition)throws Exception{
  for(int i=0;i<100;i++){if("true".equals(js(web,"Boolean("+condition+")")))return;Thread.sleep(200);}
  fail("Native payroll page did not reach "+condition+": "+js(web,"document.body.innerText"));
 }
 private void tap(WebView web,String selector)throws Exception{
  String element="document.querySelector("+JSONObject.quote(selector)+")";
  js(web,element+".scrollIntoView({block:'center',inline:'center'})");Thread.sleep(250);
  float cssX=Float.parseFloat(js(web,"((r)=>r.left+r.width/2)("+element+".getBoundingClientRect())"));
  float cssY=Float.parseFloat(js(web,"((r)=>r.top+r.height/2)("+element+".getBoundingClientRect())"));
  int[] location=new int[2];float[] scale=new float[1];
  instrumentation.runOnMainSync(()->{web.getLocationOnScreen(location);scale[0]=web.getScale();});
  float x=location[0]+cssX*scale[0],y=location[1]+cssY*scale[0];long time=SystemClock.uptimeMillis();
  MotionEvent down=MotionEvent.obtain(time,time,MotionEvent.ACTION_DOWN,x,y,0),up=MotionEvent.obtain(time,time+60,MotionEvent.ACTION_UP,x,y,0);
  try{instrumentation.sendPointerSync(down);instrumentation.sendPointerSync(up);}finally{down.recycle();up.recycle();}
 }
 @Test public void approvedPayrollUsesTheNativeSavePickerWithoutLosingTheBatch()throws Exception{
  Context context=instrumentation.getTargetContext();
  if(!Python.isStarted())Python.start(new AndroidPlatform(context));
  Python python=Python.getInstance();PyObject globals=python.getModule("builtins").callAttr("dict");
  try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
   AtomicReference<MainActivity> activity=new AtomicReference<>();scenario.onActivity(activity::set);
   Method copy=MainActivity.class.getDeclaredMethod("copyProgramAssets");copy.setAccessible(true);copy.invoke(activity.get());
   globals.callAttr("__setitem__","program_dir",new java.io.File(context.getFilesDir(),"accounting-program").getAbsolutePath());
   globals.callAttr("__setitem__","fixture_dir",new java.io.File(context.getFilesDir(),"payroll-acceptance-"+System.nanoTime()).getAbsolutePath());
   String code;try(java.io.InputStream input=instrumentation.getContext().getAssets().open("payroll_fixture.py")){code=new String(input.readAllBytes(),StandardCharsets.UTF_8);}
   python.getModule("builtins").callAttr("exec",code,globals);
   JSONObject fixture=new JSONObject(globals.callAttr("get","result").toString());String origin=EngineOrigin.local(fixture.getInt("port"));
   Field originField=MainActivity.class.getDeclaredField("origin");originField.setAccessible(true);originField.set(activity.get(),origin);
   Method open=MainActivity.class.getDeclaredMethod("openBooks");open.setAccessible(true);
   instrumentation.runOnMainSync(()->{try{CookieManager.getInstance().setCookie(origin,"bw_session="+fixture.getString("session")+"; Path=/; HttpOnly; SameSite=Strict");CookieManager.getInstance().flush();open.invoke(activity.get());}catch(Exception error){throw new RuntimeException(error);}});
   Field browserField=MainActivity.class.getDeclaredField("browser");browserField.setAccessible(true);WebView web=(WebView)browserField.get(activity.get());
   ready(web,"document.querySelector('nav [data-view=\"payrollmanagement\"]')");
   js(web,"document.querySelector('nav [data-view=\"payrollmanagement\"]').click()");
   ready(web,"document.querySelector('[data-pm=\"open\"]')");
   js(web,"document.querySelector('[data-pm=\"open\"]').click()");
   ready(web,"document.querySelector('a[data-pm-download][href*=xlsx]')");
   assertTrue(js(web,"document.body.innerText").contains("762.50"));
   Instrumentation.ActivityMonitor picker=instrumentation.addMonitor(new IntentFilter(Intent.ACTION_CREATE_DOCUMENT),new Instrumentation.ActivityResult(Activity.RESULT_CANCELED,null),true);
   try{
    tap(web,"a[data-pm-download][href*=xlsx]");
    for(int i=0;i<100&&picker.getHits()==0;i++)Thread.sleep(100);
    if(picker.getHits()!=1){
     System.out.println("Native payroll save diagnostic: "+js(web,"JSON.stringify({notice:document.querySelector('#notice')?.innerText,url:location.href,body:document.body.innerText})"));
     Field pending=MainActivity.class.getDeclaredField("downloadUrl");pending.setAccessible(true);System.out.println("Native pending export URL: "+pending.get(activity.get()));
    }
    assertEquals("The authorized XLSX must open Android's document save picker",1,picker.getHits());
    assertTrue(js(web,"document.body.innerText").contains("Payroll batch"));
    PyObject exported=python.getModule("builtins").callAttr("eval","fixture_app.ledger().db.execute('SELECT COUNT(*) FROM pm_exports').fetchone()[0]",globals);
    assertEquals("Export retries must retain one approved snapshot",1,exported.toInt());
    System.out.println("PASS Android: $762.50 payroll, actual WebView export, native save picker and one retained export snapshot.");
   }finally{instrumentation.removeMonitor(picker);}
  }finally{
   python.getModule("builtins").callAttr("exec","if 'fixture_server' in globals(): fixture_server.shutdown(); fixture_server.server_close(); fixture_app.stop.set()",globals);
  }
 }
}
