package com.backwoodsbrew.accounting;

import java.net.URI;
import java.util.Locale;

/** Exact HTTPS origin boundary, shared by setup and every navigation/download. */
public final class CompanyOrigin {
    private CompanyOrigin() {}

    public static String normalize(String value) {
        try {
            URI uri = new URI(value.trim());
            String host = uri.getHost();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null ||
                uri.getRawUserInfo() != null || uri.getRawQuery() != null ||
                uri.getRawFragment() != null ||
                !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath())) ||
                uri.getPort() == 0 || uri.getPort() > 65535)
                throw new IllegalArgumentException();
            host = host.toLowerCase(Locale.ROOT);
            if (host.equals("localhost") || host.endsWith(".localhost") ||
                host.startsWith("127.") || host.equals("[::1]") || host.equals("0.0.0.0"))
                throw new IllegalArgumentException();
            return "https://" + host + (uri.getPort() > 0 && uri.getPort() != 443 ? ":" + uri.getPort() : "");
        } catch (Exception error) {
            throw new IllegalArgumentException("Enter your company's HTTPS accounting address, for example https://books.yourcompany.com. A Firebase project ID alone is not an accounting server address.");
        }
    }

    public static boolean contains(String origin, String value) {
        try {
            URI uri = new URI(value);
            String authority = new URI(uri.getScheme(), uri.getRawAuthority(), null, null, null).toString();
            return normalize(authority).equals(origin);
        } catch (Exception error) { return false; }
    }
}
