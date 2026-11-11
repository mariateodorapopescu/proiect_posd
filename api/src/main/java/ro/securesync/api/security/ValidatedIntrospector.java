package ro.securesync.api.security;

import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import java.time.Instant;
import java.util.Map;

/** No cache: the authorization server is consulted for every authenticated request. */
public class ValidatedIntrospector implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String issuer;
    private final String audience;

    public ValidatedIntrospector(OpaqueTokenIntrospector delegate, String issuer, String audience) {
        this.delegate = delegate;
        this.issuer = issuer;
        this.audience = audience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Map<String, Object> claims = principal.getAttributes();
        String sub = TokenClaims.text(claims, "sub");
        Instant exp = timestamp(claims.get("exp"));
        Instant nbf = timestamp(claims.get("nbf"));
        if (!issuer.equals(String.valueOf(claims.get("iss"))) || sub.isBlank()
                || !TokenClaims.strings(claims.get("aud")).contains(audience)
                || exp == null || !Instant.now().isBefore(exp) || (nbf != null && Instant.now().isBefore(nbf))) {
            throw new BadOpaqueTokenException("Token claims are not valid for this API");
        }
        return new DefaultOAuth2AuthenticatedPrincipal(sub, claims, TokenClaims.authorities(claims));
    }

    private static Instant timestamp(Object value) {
        if (value instanceof Instant instant) return instant;
        if (value instanceof Number number) return Instant.ofEpochSecond(number.longValue());
        return null;
    }
}
