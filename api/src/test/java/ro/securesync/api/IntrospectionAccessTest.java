package ro.securesync.api;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.*;
import org.springframework.test.context.*;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import ro.securesync.api.security.TokenClaims;

import java.nio.file.Path;
import java.util.Map;
import java.util.List;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:securesync_introspection;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa", "spring.datasource.password=", "spring.datasource.driver-class-name=org.h2.Driver"
})
@ActiveProfiles("introspection")
@AutoConfigureMockMvc
class IntrospectionAccessTest {
    @TempDir static Path storage;
    @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) {
        registry.add("app.storage-root", () -> storage.toString());
    }
    @Autowired MockMvc mvc;
    @MockitoBean OpaqueTokenIntrospector introspector;

    @Test void introspectionProfileUsesEveryRequestAndRejectsInactiveTokens() throws Exception {
        Map<String, Object> claims = Map.of("sub", "test-id", "preferred_username", "test-user", "department", "IT",
                "realm_access", Map.of("roles", List.of("USER")), "scope", List.of("documents:read"));
        when(introspector.introspect("active")).thenReturn(
                new DefaultOAuth2AuthenticatedPrincipal("test-id", claims, TokenClaims.authorities(claims)));
        when(introspector.introspect("inactive")).thenThrow(new BadOpaqueTokenException("Inactive test token"));
        mvc.perform(get("/api/me")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/me").header(HttpHeaders.AUTHORIZATION, "Bearer active"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.strategy").value("introspection"))
                .andExpect(jsonPath("$.sub").value("test-id"));
        mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer active"))
                .andExpect(status().isOk());
        verify(introspector, times(2)).introspect("active");
        mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer inactive"))
                .andExpect(status().isUnauthorized());
    }
}
