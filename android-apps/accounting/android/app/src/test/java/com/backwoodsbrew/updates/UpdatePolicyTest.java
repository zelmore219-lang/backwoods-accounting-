package com.backwoodsbrew.updates;
import org.junit.Test;
import static org.junit.Assert.*;
public class UpdatePolicyTest {
 @Test public void onlyNewerVersionsAreOffered(){assertTrue(UpdatePolicy.newer("1.0.10","1.0.9"));assertFalse(UpdatePolicy.newer("1.0.4","1.0.4"));assertFalse(UpdatePolicy.newer("1.0.3","1.0.4"));}
 @Test public void officialRepositoryIsAllowed(){assertEquals(UpdatePolicy.FEED,UpdatePolicy.trusted(UpdatePolicy.FEED));}
 @Test public void untrustedFeedsAreRejected(){for(String url:new String[]{"http://github.com/zelmore219-lang/backwoods-accounting-/releases/download/v/a.apk","https://github.com/evil/repo/releases/download/v/a.apk","https://github.com.attacker.test/a.apk","https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/../a.apk"}){try{UpdatePolicy.trusted(url);fail(url);}catch(IllegalArgumentException expected){}}}
 @Test public void untrustedRedirectsAndInvalidDigestsAreRejected(){try{UpdatePolicy.redirect("https://attacker.test/a.apk");fail();}catch(IllegalArgumentException expected){}assertFalse(UpdatePolicy.digest("bad"));assertTrue(UpdatePolicy.digest("a".repeat(64)));}
}
