package com.backwoodsbrew.accounting;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Authenticated company discovery. No server URL is requested from the user. */
public final class FirebaseDiscovery {
    public static final class Company {
        public final String origin, idToken;
        Company(String origin,String idToken) { this.origin=origin;this.idToken=idToken; }
    }
    private static JSONObject request(String url,JSONObject body,String token) throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection();
        connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(15000);
        try {
            if(token!=null)connection.setRequestProperty("Authorization","Bearer "+token);
            if(body!=null){
                connection.setRequestMethod("POST");connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type","application/json");
                try(java.io.OutputStream stream=connection.getOutputStream()){stream.write(body.toString().getBytes(StandardCharsets.UTF_8));}
            }
            int status=connection.getResponseCode();
            if(status==404)throw new Exception("Your company accounting service is not set up yet. Its administrator must finish the one-time Firebase deployment.");
            if(status==403)throw new Exception("Your Firebase account cannot read the accounting connection. The administrator must check the accounting security rules.");
            if(status<200||status>=300)throw new Exception("Company sign-in or discovery failed. Check the email, password and company setup ("+status+").");
            try(InputStream stream=connection.getInputStream();ByteArrayOutputStream bytes=new ByteArrayOutputStream()){
                byte[] buffer=new byte[8192];int n;
                while((n=stream.read(buffer))!=-1){bytes.write(buffer,0,n);if(bytes.size()>131072)throw new Exception("Unexpected company connection response.");}
                return new JSONObject(bytes.toString("UTF-8"));
            }
        }finally{connection.disconnect();}
    }
    public static Company signIn(String email,String password) throws Exception {
        JSONObject result=request("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="+FirebaseProject.API_KEY,
            new JSONObject().put("email",email).put("password",password).put("returnSecureToken",true),null);
        String uid=result.getString("localId"),token=result.getString("idToken");
        if(!uid.matches("[-A-Za-z0-9_]{1,128}"))throw new Exception("Unsupported Firebase company account.");
        JSONObject document=request("https://firestore.googleapis.com/v1/projects/"+FirebaseProject.PROJECT_ID+
            "/databases/(default)/documents/businessAccounting/"+uid+"/settings/service",null,token);
        String origin=CompanyOrigin.normalize(document.getJSONObject("fields").getJSONObject("origin").getString("stringValue"));
        return new Company(origin,token);
    }
}
