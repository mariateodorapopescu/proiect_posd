package ro.securesync.api.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.MediaType;

import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class TokenValidationTest {
    private static final String ISSUER = "http://localhost:8080/realms/securesync";

    @Test void jwtRequiresCorrectAudienceIssuerAndUnexpiredTokenWithoutLeeway() {
        var validator = new DelegatingOAuth2TokenValidator<>(new JwtTimestampValidator(Duration.ZERO),
                new JwtIssuerValidator(ISSUER), new AudienceValidator("securesync-api"));
        assertFalse(validator.validate(jwt(ISSUER, "securesync-api", Instant.now().plusSeconds(60))).hasErrors());
        assertTrue(validator.validate(jwt(ISSUER, "another-api", Instant.now().plusSeconds(60))).hasErrors());
        assertTrue(validator.validate(jwt("http://wrong.example/realm", "securesync-api", Instant.now().plusSeconds(60))).hasErrors());
        assertTrue(validator.validate(jwt(ISSUER, "securesync-api", Instant.now().minusMillis(1))).hasErrors());
    }

    @Test void introspectionIsUncachedAndNormalizesRolesAndScopes() {
        AtomicInteger calls = new AtomicInteger();
        OpaqueTokenIntrospector delegate = token -> {
            calls.incrementAndGet();
            return principal(claims());
        };
        var introspector = new ValidatedIntrospector(delegate, ISSUER, "securesync-api");
        var principal = introspector.introspect("token");
        introspector.introspect("token");
        assertEquals(2, calls.get());
        Set<String> authorities = new HashSet<>();
        principal.getAuthorities().forEach(a -> authorities.add(a.getAuthority()));
        assertTrue(authorities.containsAll(Set.of("ROLE_USER", "SCOPE_documents:read", "SCOPE_documents:write")));
    }

    @Test void introspectionRejectsWrongIssuerAudienceExpiryAndMissingIdentity() {
        for (var invalid : List.of(Map.entry("iss", "https://wrong.example"),
                Map.entry("aud", List.of("another-api")), Map.entry("exp", Instant.now().minusSeconds(1)), Map.entry("sub", ""))) {
            Map<String, Object> attributes = claims();
            attributes.put(invalid.getKey(), invalid.getValue());
            var introspector = new ValidatedIntrospector(token -> principal(attributes), ISSUER, "securesync-api");
            assertThrows(BadOpaqueTokenException.class, () -> introspector.introspect("token"));
        }
    }

    @Test void introspectionDoesNotFallBackToJwtWhenAuthorizationServerRejectsToken() {
        var introspector = new ValidatedIntrospector(token -> { throw new BadOpaqueTokenException("inactive"); },
                ISSUER, "securesync-api");
        assertThrows(BadOpaqueTokenException.class, () -> introspector.introspect("signed-but-revoked-jwt"));
    }

    @Test void realIntrospectionResponseKeepsDepartmentRolesIssuerAndAudience() {
        RestTemplate rest = new RestTemplate();
        var server = MockRestServiceServer.createServer(rest);
        long expires = Instant.now().plusSeconds(60).getEpochSecond();
        server.expect(requestTo("http://keycloak.example/introspect")).andRespond(withSuccess("""
                {"active":true,"sub":"user-id","iss":"%s","aud":["securesync-api"],
                 "exp":%d,"scope":"documents:read documents:write","department":"IT",
                 "realm_access":{"roles":["USER"]}}
                """.formatted(ISSUER, expires), MediaType.APPLICATION_JSON));
        var introspector = new ValidatedIntrospector(new SpringOpaqueTokenIntrospector(
                "http://keycloak.example/introspect", rest), ISSUER, "securesync-api");
        var principal = introspector.introspect("test");
        assertEquals("IT", principal.getAttribute("department"));
        assertTrue(principal.getAuthorities().stream().anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
        server.verify();
    }

    private static Jwt jwt(String issuer, String audience, Instant expiry) {
        return Jwt.withTokenValue("test").header("alg", "RS256").subject("user-id").issuer(issuer)
                .audience(List.of(audience)).issuedAt(Instant.now().minusSeconds(120)).expiresAt(expiry).build();
    }

    private static Map<String, Object> claims() {
        Map<String, Object> claims = new HashMap<>();
        claims.put("active", true);
        claims.put("sub", "user-id");
        claims.put("iss", ISSUER);
        claims.put("aud", List.of("securesync-api"));
        claims.put("exp", Instant.now().plusSeconds(60));
        claims.put("scope", List.of("documents:read", "documents:write"));
        claims.put("realm_access", Map.of("roles", List.of("USER")));
        return claims;
    }

    private static OAuth2AuthenticatedPrincipal principal(Map<String, Object> attributes) {
        return new DefaultOAuth2AuthenticatedPrincipal("user-id", attributes, List.of());
    }
}
