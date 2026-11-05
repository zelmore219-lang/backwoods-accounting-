package com.backwoodsbrew.accounting;

import java.net.URI;

/** The browser can only navigate inside the engine this app started. */
public final class EngineOrigin {
    private EngineOrigin() {}
    public static String local(int port) {
        if(port<1||port>65535)throw new IllegalArgumentException("Invalid local engine port");
        return "http://127.0.0.1:"+port;
    }
    public static boolean contains(String origin,String value) {
        try{
            URI expected=new URI(origin),actual=new URI(value);
            return "http".equals(expected.getScheme())&&"127.0.0.1".equals(expected.getHost())
                &&expected.getPort()>0&&"http".equals(actual.getScheme())&&"127.0.0.1".equals(actual.getHost())
                &&actual.getRawUserInfo()==null&&actual.getPort()==expected.getPort();
        }catch(Exception error){return false;}
    }
}
