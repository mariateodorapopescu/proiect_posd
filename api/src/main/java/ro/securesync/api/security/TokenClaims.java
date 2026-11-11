package ro.securesync.api.security;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.*;

/** Both validation strategies derive authorities only from the trusted token response. */
public final class TokenClaims {
    private TokenClaims() { }

    public static Set<String> strings(Object value) {
        if (value instanceof String text) return new LinkedHashSet<>(Arrays.stream(text.split("\\s+"))
                .filter(s -> !s.isBlank()).toList());
        if (value instanceof Collection<?> values) {
            Set<String> result = new LinkedHashSet<>();
            values.stream().filter(String.class::isInstance).map(String.class::cast)
                    .filter(s -> !s.isBlank()).forEach(result::add);
            return result;
        }
        return Set.of();
    }

    public static Set<String> roles(Map<String, Object> claims) {
        Object realm = claims.get("realm_access");
        return realm instanceof Map<?, ?> access ? strings(access.get("roles")) : Set.of();
    }

    public static Collection<GrantedAuthority> authorities(Map<String, Object> claims) {
        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        strings(claims.get("scope")).stream().filter(s -> !s.isBlank())
                .map(s -> new SimpleGrantedAuthority("SCOPE_" + s)).forEach(authorities::add);
        roles(claims).stream().map(r -> new SimpleGrantedAuthority("ROLE_" + r)).forEach(authorities::add);
        return authorities;
    }

    public static String text(Map<String, Object> claims, String name) {
        Object value = claims.get(name);
        return value instanceof String text ? text : "";
    }
}
