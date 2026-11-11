package ro.securesync.api;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import ro.securesync.api.documents.DocumentRepository;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:securesync;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa", "spring.datasource.password=", "spring.datasource.driver-class-name=org.h2.Driver",
        "app.cors-origins=http://localhost:3001,http://localhost:3002"
})
@AutoConfigureMockMvc
class DocumentAccessTest {
    @TempDir static Path storage;
    @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) {
        registry.add("app.storage-root", () -> storage.toString());
    }
    @Autowired MockMvc mvc;
    @Autowired DocumentRepository documents;
    @MockitoBean JwtDecoder decoder;

    @BeforeEach void prepare() {
        documents.deleteAll();
        token("alice", "alice-id", "IT", List.of("USER"), "documents:read documents:write");
        token("colleague", "colleague-id", "IT", List.of("USER"), "documents:read documents:write");
        token("outsider", "outsider-id", "HR", List.of("USER"), "documents:read documents:write");
        token("admin", "admin-id", "SECURITY", List.of("ADMIN"), "documents:read documents:write");
        token("no-scope", "alice-id", "IT", List.of("ADMIN"), "openid");
        token("no-role", "alice-id", "IT", List.of(), "documents:read documents:write");
        token("no-department", "alice-id", "", List.of("USER"), "documents:read documents:write");
        when(decoder.decode("invalid")).thenThrow(new BadJwtException("Invalid test token"));
    }

    @Test void missingOrInvalidTokenReturns401AndHealthIsPublic() throws Exception {
        mvc.perform(get("/api/health")).andExpect(status().isOk()).andExpect(jsonPath("$.strategy").value("jwt"));
        mvc.perform(get("/api/documents")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/me").header(HttpHeaders.AUTHORIZATION, "Bearer invalid")).andExpect(status().isUnauthorized());
        mvc.perform(get("/files/doc_00000000-0000-0000-0000-000000000000.pdf")).andExpect(status().isUnauthorized());
    }

    @Test void scopeAndRoleAreBothRequiredEvenForAdministrator() throws Exception {
        mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer no-scope")).andExpect(status().isForbidden());
        mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer no-role")).andExpect(status().isForbidden());
        mvc.perform(multipart("/api/documents").file(pdf()).param("title", "Policy")
                .header(HttpHeaders.AUTHORIZATION, "Bearer no-scope")).andExpect(status().isForbidden());
        mvc.perform(multipart("/api/documents").file(pdf()).param("title", "Policy")
                .header(HttpHeaders.AUTHORIZATION, "Bearer no-department")).andExpect(status().isForbidden());
    }

    @Test void ownerDepartmentAndAdminCanReadButOnlyOwnerOrAdminCanDelete() throws Exception {
        long id = upload("alice");
        for (String token : List.of("alice", "colleague", "admin")) {
            mvc.perform(get("/api/documents/{id}/download", id).header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                    .andExpect(status().isOk()).andExpect(content().contentType("application/pdf"))
                    .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                    .andExpect(content().bytes(pdf().getBytes()));
        }
        mvc.perform(get("/api/documents/{id}/download", id).header(HttpHeaders.AUTHORIZATION, "Bearer outsider"))
                .andExpect(status().isForbidden());
        for (String token : List.of("outsider", "colleague")) {
            mvc.perform(delete("/api/documents/{id}", id).header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                    .andExpect(status().isForbidden());
        }
        mvc.perform(delete("/api/documents/{id}", id).header(HttpHeaders.AUTHORIZATION, "Bearer alice"))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/documents/{id}/download", id).header(HttpHeaders.AUTHORIZATION, "Bearer alice"))
                .andExpect(status().isNotFound());
    }

    @Test void listingFiltersDocumentsAndUploadIgnoresClientOwnership() throws Exception {
        upload("alice");
        for (String token : List.of("alice", "colleague", "admin")) {
            mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                    .andExpect(status().isOk()).andExpect(jsonPath("$", hasSize(1)))
                    .andExpect(jsonPath("$[0].ownerId").value("alice-id"))
                    .andExpect(jsonPath("$[0].department").value("IT"))
                    .andExpect(jsonPath("$[0].storageKey").doesNotExist());
        }
        mvc.perform(get("/api/documents").header(HttpHeaders.AUTHORIZATION, "Bearer outsider"))
                .andExpect(status().isOk()).andExpect(jsonPath("$", hasSize(0)));
        mvc.perform(get("/api/me").header(HttpHeaders.AUTHORIZATION, "Bearer alice"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.sub").value("alice-id"))
                .andExpect(jsonPath("$.roles", contains("USER")))
                .andExpect(jsonPath("$.scopes", hasItem("documents:read")));
    }

    @Test void adminCanDeleteAndMissingDepartmentDoesNotGrantDepartmentAccess() throws Exception {
        long id = upload("alice");
        token("blank", "blank-id", "", List.of("USER"), "documents:read documents:write");
        mvc.perform(get("/api/documents/{id}/download", id).header(HttpHeaders.AUTHORIZATION, "Bearer blank"))
                .andExpect(status().isForbidden());
        mvc.perform(delete("/api/documents/{id}", id).header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
                .andExpect(status().isNoContent());
    }

    @Test void invalidFilesAndTitlesAreRejectedWithoutDatabaseRows() throws Exception {
        for (MockMultipartFile file : List.of(
                new MockMultipartFile("file", "fake.pdf", "application/pdf", "not a pdf".getBytes()),
                new MockMultipartFile("file", "fake.pdf", "text/plain", "%PDF-1.7".getBytes()),
                new MockMultipartFile("file", "empty.pdf", "application/pdf", new byte[0]))) {
            mvc.perform(multipart("/api/documents").file(file).param("title", "A document")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer alice")).andExpect(status().isBadRequest());
        }
        mvc.perform(multipart("/api/documents").file(pdf()).param("title", " ")
                .header(HttpHeaders.AUTHORIZATION, "Bearer alice")).andExpect(status().isBadRequest());
        Assertions.assertEquals(0, documents.count());
    }

    @Test void corsAllowsOnlyConfiguredApplications() throws Exception {
        mvc.perform(options("/api/documents").header("Origin", "http://localhost:3001")
                .header("Access-Control-Request-Method", "GET").header("Access-Control-Request-Headers", "authorization"))
                .andExpect(status().isOk()).andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:3001"));
        mvc.perform(options("/api/documents").header("Origin", "https://unrelated.example")
                .header("Access-Control-Request-Method", "GET")).andExpect(status().isForbidden());
    }

    private long upload(String token) throws Exception {
        String json = mvc.perform(multipart("/api/documents").file(pdf()).param("title", "Security policy")
                        .param("ownerId", "attacker-choice").param("department", "attacker-choice")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.originalFilename").value("policy.pdf"))
                .andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(json).get("id").asLong();
    }

    private static MockMultipartFile pdf() {
        return new MockMultipartFile("file", "../policy.pdf", "application/pdf", "%PDF-1.7\nSecureSync fixture\n%%EOF".getBytes());
    }

    private void token(String token, String subject, String department, List<String> roles, String scopes) {
        Jwt jwt = Jwt.withTokenValue(token).header("alg", "RS256").subject(subject)
                .issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60))
                .claim("preferred_username", token).claim("department", department)
                .claim("realm_access", Map.of("roles", roles)).claim("scope", scopes).build();
        when(decoder.decode(token)).thenReturn(jwt);
    }
}
