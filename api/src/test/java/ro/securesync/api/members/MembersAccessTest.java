package ro.securesync.api.members;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:members;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa", "spring.datasource.password=", "spring.datasource.driver-class-name=org.h2.Driver"
})
@AutoConfigureMockMvc
class MembersAccessTest {
    @TempDir static Path storage;
    @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) {
        registry.add("app.storage-root", () -> storage.toString());
    }
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder decoder;
    @MockitoBean MemberManagementService service;

    @BeforeEach void prepare() {
        for (String role : List.of("USER", "ADMIN", "IMPLEMENTATOR")) token(role, role, "members:manage");
        token("no-scope", "IMPLEMENTATOR", "documents:read");
        when(service.list(any(), anyString(), anyInt())).thenReturn(new MemberManagementService.Page(List.of(), 0, false));
        when(service.update(any(), anyString(), any())).thenReturn(new MemberManagementService.Member(
                MemberManagementServiceTest.TARGET, "member", "IT", List.of("ADMIN"), true));
    }

    @Test void authenticationAndBothAuthoritiesAreRequired() throws Exception {
        mvc.perform(get("/api/members")).andExpect(status().isUnauthorized());
        for (String denied : List.of("USER", "ADMIN", "no-scope")) {
            mvc.perform(get("/api/members").header(HttpHeaders.AUTHORIZATION, "Bearer " + denied)).andExpect(status().isForbidden());
            mvc.perform(put("/api/members/{id}/access", MemberManagementServiceTest.TARGET)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + denied).contentType("application/json")
                    .content("{\"roles\":[\"ADMIN\"],\"department\":\"IT\"}")).andExpect(status().isForbidden());
        }
        verifyNoInteractions(service);
    }

    @Test void implementatorCanListAndUpdateThroughGuardedController() throws Exception {
        mvc.perform(get("/api/members").header(HttpHeaders.AUTHORIZATION, "Bearer IMPLEMENTATOR"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.members").isArray()).andExpect(jsonPath("$.hasMore").value(false));
        mvc.perform(put("/api/members/{id}/access", MemberManagementServiceTest.TARGET)
                .header(HttpHeaders.AUTHORIZATION, "Bearer IMPLEMENTATOR").contentType("application/json")
                .content("{\"roles\":[\"ADMIN\"],\"department\":\"IT\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.roles[0]").value("ADMIN"));
    }

    @Test void malformedRequestsReturn400AndCorsPermitsPut() throws Exception {
        mvc.perform(put("/api/members/{id}/access", MemberManagementServiceTest.TARGET)
                .header(HttpHeaders.AUTHORIZATION, "Bearer IMPLEMENTATOR").contentType("application/json").content("{broken"))
                .andExpect(status().isBadRequest());
        mvc.perform(options("/api/members/{id}/access", MemberManagementServiceTest.TARGET)
                .header("Origin", "http://localhost:3002").header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers", "authorization,content-type"))
                .andExpect(status().isOk()).andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:3002"));
    }

    private void token(String token, String role, String scopes) {
        when(decoder.decode(token)).thenReturn(Jwt.withTokenValue(token).header("alg", "RS256")
                .subject(MemberManagementServiceTest.ACTOR).issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60))
                .claim("realm_access", Map.of("roles", List.of(role))).claim("scope", scopes).build());
    }
}
