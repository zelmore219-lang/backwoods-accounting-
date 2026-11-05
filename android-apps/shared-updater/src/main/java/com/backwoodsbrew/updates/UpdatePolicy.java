package com.backwoodsbrew.updates;

import java.net.URI;

public final class UpdatePolicy {
    public static final String FEED="https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/app-updates/backwoods-updates.json";
    private static final String PREFIX="/zelmore219-lang/backwoods-accounting-/releases/download/";
    private UpdatePolicy() {}
    public static boolean newer(String a,String b) {
        long[] x=parts(a),y=parts(b);
        for(int i=0;i<3;i++) if(x[i]!=y[i])return x[i]>y[i];
        return false;
    }
    private static long[] parts(String value) {
        if(value==null||!value.matches("[0-9]+\\.[0-9]+\\.[0-9]+"))throw new IllegalArgumentException("Invalid update version");
        String[] s=value.split("\\.");return new long[]{Long.parseLong(s[0]),Long.parseLong(s[1]),Long.parseLong(s[2])};
    }
    public static String trusted(String value) {
        URI u=URI.create(value);
        if(!"https".equals(u.getScheme())||!"github.com".equals(u.getHost())||u.getPort()!=-1||u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||!u.getPath().startsWith(PREFIX)||!u.normalize().getPath().equals(u.getPath()))throw new IllegalArgumentException("Use an HTTPS release download from the Backwoods accounting repository.");
        return value;
    }
    public static String redirect(String value) {
        URI u=URI.create(value);String host=u.getHost();
        if(!"https".equals(u.getScheme())||u.getPort()!=-1||u.getUserInfo()!=null||!("github.com".equals(host)||"release-assets.githubusercontent.com".equals(host)||"objects.githubusercontent.com".equals(host)))throw new IllegalArgumentException("Untrusted update redirect");
        return value;
    }
    public static boolean digest(String value) {return value!=null&&value.matches("[a-f0-9]{64}");}
}
