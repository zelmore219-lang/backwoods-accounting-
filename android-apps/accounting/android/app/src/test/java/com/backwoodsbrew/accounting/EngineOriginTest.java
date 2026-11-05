package com.backwoodsbrew.accounting;

import org.junit.Test;
import static org.junit.Assert.*;

public class EngineOriginTest {
    @Test public void onlyValidLocalPorts() {
        assertEquals("http://127.0.0.1:12345",EngineOrigin.local(12345));
        for(int port:new int[]{-1,0,65536})try{EngineOrigin.local(port);fail();}catch(IllegalArgumentException expected){}
    }
    @Test public void localApplicationNavigationWorks() {
        String origin=EngineOrigin.local(12345);
        assertTrue(EngineOrigin.contains(origin,origin+"/"));
        assertTrue(EngineOrigin.contains(origin,origin+"/api/state?date=2026-11-04"));
        assertTrue(EngineOrigin.contains(origin,origin+"/print?type=record"));
    }
    @Test public void otherPortsAndExternalOriginsAreBlocked() {
        String origin=EngineOrigin.local(12345);
        for(String value:new String[]{"http://127.0.0.1:12346/","http://localhost:12345/","http://127.0.0.1.evil.test:12345/","http://user@127.0.0.1:12345/","https://example.test/","file:///data/data/private","javascript:alert(1)"})
            assertFalse(value,EngineOrigin.contains(origin,value));
    }
}
