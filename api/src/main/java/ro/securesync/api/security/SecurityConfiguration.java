package ro.securesync.api.security;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.introspection.*;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.cors.*;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, @Value("${app.token-strategy:jwt}") String strategy,
                                            ObjectProvider<JwtDecoder> decoder,
                                            ObjectProvider<OpaqueTokenIntrospector> introspector) throws Exception {
        http.csrf(AbstractHttpConfigurer::disable)
                .cors(cors -> { })
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                        .anyRequest().authenticated());
        if ("jwt".equals(strategy)) {
            JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
            converter.setJwtGrantedAuthoritiesConverter(jwt -> TokenClaims.authorities(jwt.getClaims()));
            http.oauth2ResourceServer(resource -> resource.jwt(jwt -> jwt.decoder(decoder.getObject())
                    .jwtAuthenticationConverter(converter)));
        } else if ("introspection".equals(strategy)) {
            http.oauth2ResourceServer(resource -> resource.opaqueToken(opaque -> opaque.introspector(introspector.getObject())));
        } else throw new IllegalStateException("Unknown token strategy");
        return http.build();
    }

    @Bean
    @Profile("!introspection")
    JwtDecoder jwtDecoder(@Value("${app.issuer}") String issuer, @Value("${app.jwk-set-uri}") String jwks,
                          @Value("${app.audience}") String audience) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        // Zero leeway keeps the measured expiry window honest; all Compose services share one host clock.
        JwtTimestampValidator timestamps = new JwtTimestampValidator(Duration.ZERO);
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(timestamps, new JwtIssuerValidator(issuer),
                new AudienceValidator(audience)));
        return decoder;
    }

    @Bean
    @Profile("introspection")
    OpaqueTokenIntrospector opaqueTokenIntrospector(@Value("${app.introspection-uri}") String uri,
            @Value("${app.introspection-client-id}") String clientId,
            @Value("${app.introspection-client-secret}") String secret,
            @Value("${app.issuer}") String issuer, @Value("${app.audience}") String audience) {
        // HTTP/1.1 on purpose: with the JDK default (HTTP/2) the introspection calls share few connections and,
        // under concurrent load, fail with "too many concurrent streams" (surfacing as 401 via /error).
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3)).build());
        factory.setReadTimeout(Duration.ofSeconds(3));
        RestTemplate rest = new RestTemplate(factory);
        rest.getInterceptors().add(new BasicAuthenticationInterceptor(clientId, secret));
        return new ValidatedIntrospector(new SpringOpaqueTokenIntrospector(uri, rest), issuer, audience);
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(@Value("${app.cors-origins}") String origins) {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(Arrays.stream(origins.split(",")).map(String::trim).toList());
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        config.setExposedHeaders(List.of("Content-Disposition"));
        config.setAllowCredentials(false);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
