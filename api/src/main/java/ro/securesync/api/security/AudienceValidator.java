package ro.securesync.api.security;

import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.Jwt;

public class AudienceValidator implements OAuth2TokenValidator<Jwt> {
    private final String audience;
    public AudienceValidator(String audience) { this.audience = audience; }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience() != null && jwt.getAudience().contains(audience) && jwt.getSubject() != null && !jwt.getSubject().isBlank()
                && jwt.getExpiresAt() != null) return OAuth2TokenValidatorResult.success();
        return OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Required token claims are missing", null));
    }
}
