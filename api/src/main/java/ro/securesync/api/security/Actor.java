package ro.securesync.api.security;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.Map;
import java.util.Set;

public record Actor(String sub, String username, String department, Set<String> roles, Set<String> scopes) {
    public static Actor from(Authentication authentication) {
        Object principal = authentication.getPrincipal();
        Map<String, Object> claims;
        if (principal instanceof Jwt jwt) claims = jwt.getClaims();
        else if (principal instanceof OAuth2AuthenticatedPrincipal oauth) claims = oauth.getAttributes();
        else throw new AccessDeniedException("Token identity is required");
        String sub = TokenClaims.text(claims, "sub");
        if (sub.isBlank()) throw new AccessDeniedException("Token subject is required");
        return new Actor(sub, TokenClaims.text(claims, "preferred_username"),
                TokenClaims.text(claims, "department"), TokenClaims.roles(claims), TokenClaims.strings(claims.get("scope")));
    }

    public boolean admin() { return roles.contains("ADMIN"); }
}
