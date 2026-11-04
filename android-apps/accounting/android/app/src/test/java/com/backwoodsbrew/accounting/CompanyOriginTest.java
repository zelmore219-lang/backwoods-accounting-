package com.backwoodsbrew.accounting;

import org.junit.Test;
import static org.junit.Assert.*;

public class CompanyOriginTest {
    @Test public void normalizesSecureOrigin() {
        assertEquals("https://books.example.com",CompanyOrigin.normalize(" https://BOOKS.example.com:443/ "));
        assertEquals("https://books.example.com:8443",CompanyOrigin.normalize("https://books.example.com:8443"));
    }
    @Test public void rejectsWrongEndpoints() {
        for (String value : new String[]{"http://books.example.com", "https://owner:secret@books.example.com", "https://books.example.com/path", "https://books.example.com?x=1", "https://books.example.com#fragment", "https://localhost", "https://127.0.0.1", "https://[::1]", "https://books.example.com:0", "https://books.example.com:99999", "firebase-project"}) {
            try { CompanyOrigin.normalize(value); fail("Accepted " + value); }
            catch (IllegalArgumentException expected) {}
        }
    }
    @Test public void confinesAuthenticatedNavigation() {
        String origin="https://books.example.com";
        assertTrue(CompanyOrigin.contains(origin,origin+"/api/state?date=2026-11-04"));
        assertTrue(CompanyOrigin.contains(origin,"https://books.example.com:443/print"));
        for (String value : new String[]{"http://books.example.com", "https://books.example.com.evil.test", "https://evil.test@books.example.com", "https://books.example.com:8443", "javascript:alert(1)", "file:///data/data/secrets"})
            assertFalse(value,CompanyOrigin.contains(origin,value));
    }
}
